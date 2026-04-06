import { useEffect, useRef } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../app/auth";

const CLAIM_SYNC_STORAGE_KEY = "qc_claim_refresh_signal";
const CLAIM_SYNC_CHANNEL = "qc_claim_events";

const RELOAD_PAGES = [
  "dashboard",
  "assigned-cases",
  "assign-cases",
  "upload-document",
  "completed-not-uploaded",
  "completed-uploaded",
  "audit-claims",
  "withdrawn-claims",
];

function targetPageAfterCompletion(role) {
  if (role === "doctor") return "assigned-cases";
  if (role === "user") return "upload-document";
  if (role === "auditor") return "audit-claims";
  return "dashboard";
}

function shouldReloadForPage(page) {
  return RELOAD_PAGES.includes(page);
}

export function useClaimSync() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { page } = useParams();
  const channelRef = useRef(null);
  const boundRef = useRef(false);

  const currentPage = page || "dashboard";
  const role = String(user?.role || "user");

  useEffect(() => {
    if (boundRef.current) return;
    boundRef.current = true;

    function handleSyncPayload(payload) {
      if (!payload || typeof payload !== "object") return;
      const type = String(payload.type || "").trim();
      if (!type || (type !== "claim-status-updated" && type !== "qc-updated")) return;

      if (type === "claim-status-updated") {
        const status = String(payload.status || "").trim().toLowerCase();
        if (status === "completed" && currentPage === "case-detail") {
          const searchParams = new URLSearchParams(window.location.search || "");
          const currentClaimUuid = String(searchParams.get("claim_uuid") || "").trim();
          const payloadClaimUuid = String(payload.claim_uuid || "").trim();

          if (!payloadClaimUuid || !currentClaimUuid || payloadClaimUuid === currentClaimUuid) {
            const targetPage = targetPageAfterCompletion(role);
            navigate(`/app/${targetPage}`, { replace: true });
            return;
          }
        }
      }

      if (shouldReloadForPage(currentPage)) {
        window.location.reload();
      }
    }

    // Listen for postMessage events
    function handleMessage(event) {
      try {
        if (!event || event.origin !== window.location.origin) return;
        handleSyncPayload(event.data && typeof event.data === "object" ? event.data : null);
      } catch (_err) {
        // Ignore parse errors
      }
    }

    // Listen for storage events
    function handleStorage(event) {
      try {
        if (!event || event.key !== CLAIM_SYNC_STORAGE_KEY || !event.newValue) return;
        const payload = JSON.parse(String(event.newValue || "{}"));
        handleSyncPayload(payload);
      } catch (_err) {
        // Ignore parse errors
      }
    }

    // Listen for BroadcastChannel events
    try {
      if (typeof window.BroadcastChannel === "function") {
        channelRef.current = new window.BroadcastChannel(CLAIM_SYNC_CHANNEL);
        channelRef.current.onmessage = function (event) {
          try {
            const payload = event && event.data && typeof event.data === "object" ? event.data : null;
            handleSyncPayload(payload);
          } catch (_err) {
            // Ignore parse errors
          }
        };
      }
    } catch (_err) {
      // BroadcastChannel not supported
    }

    window.addEventListener("message", handleMessage);
    window.addEventListener("storage", handleStorage);

    return () => {
      window.removeEventListener("message", handleMessage);
      window.removeEventListener("storage", handleStorage);
      if (channelRef.current) {
        try {
          channelRef.current.close();
        } catch (_err) {
          // Ignore
        }
        channelRef.current = null;
      }
    };
  }, [currentPage, role, navigate]);

  // Utility to broadcast claim update
  function broadcastClaimUpdate(payload) {
    // Store in localStorage for storage event listeners
    try {
      localStorage.setItem(CLAIM_SYNC_STORAGE_KEY, JSON.stringify(payload));
    } catch (_err) {
      // Storage may be blocked
    }

    // Broadcast via BroadcastChannel
    try {
      if (channelRef.current && typeof channelRef.current.postMessage === "function") {
        channelRef.current.postMessage(payload);
      }
    } catch (_err) {
      // Channel may be closed
    }

    // Broadcast via postMessage to other tabs (if opener exists)
    try {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(payload, window.location.origin);
      }
    } catch (_err) {
      // Opener may not exist or be cross-origin
    }
  }

  return broadcastClaimUpdate;
}
