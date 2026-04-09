import { useState, useCallback } from "react";
import { openInNewTab, isPopupAllowed } from "../lib/popup-permission";
import PopupPermissionModal from "../components/PopupPermissionModal";

/**
 * usePopupPermission Hook
 * 
 * Provides an easy way to handle popup permission with automatic modal display.
 * 
 * Usage:
 * const { openTab, PopupModal, checkPermission } = usePopupPermission();
 * 
 * // Open a URL (automatically shows modal if blocked)
 * openTab('https://example.com');
 * 
 * // Check if popups are allowed
 * if (!checkPermission()) {
 *   // Do something
 * }
 */
export default function usePopupPermission() {
  const [showPermissionModal, setShowPermissionModal] = useState(false);

  const openTab = useCallback((url, options = {}) => {
    const { onBlocked, ...openOptions } = options;
    
    const result = openInNewTab(url, openOptions);
    
    if (!result) {
      // Popup was blocked
      setShowPermissionModal(true);
      onBlocked?.();
    }
    
    return result;
  }, []);

  const checkPermission = useCallback(() => {
    return isPopupAllowed();
  }, []);

  const handleCloseModal = useCallback(() => {
    setShowPermissionModal(false);
  }, []);

  const showManualModal = useCallback(() => {
    setShowPermissionModal(true);
  }, []);

  const PopupModal = useCallback(
    (props) => (
      <PopupPermissionModal
        visible={showPermissionModal}
        onClose={handleCloseModal}
        {...props}
      />
    ),
    [showPermissionModal, handleCloseModal]
  );

  return {
    openTab,
    checkPermission,
    showManualModal,
    PopupModal,
    isShowingModal: showPermissionModal,
  };
}
