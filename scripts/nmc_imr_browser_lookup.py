#!/usr/bin/env python3
"""
NMC IMR registration lookup via browser automation (Playwright).

Example:
  python scripts/nmc_imr_browser_lookup.py --registration-number 12345
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_IMR_URL = "https://www.nmc.org.in/information-desk/indian-medical-register/1000/"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search NMC IMR by doctor registration number using browser automation."
    )
    parser.add_argument(
        "--registration-number",
        required=True,
        help="Doctor registration number to search (e.g. DMC/12345).",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_IMR_URL,
        help=f"IMR page URL (default: {DEFAULT_IMR_URL})",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=60000,
        help="Timeout per browser operation in milliseconds (default: 60000).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=50,
        help="Max table rows to include in output (default: 50).",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run with visible browser window (default is headless).",
    )
    parser.add_argument(
        "--save-html",
        default="",
        help="Optional path to save final page HTML for debugging.",
    )
    parser.add_argument(
        "--save-screenshot",
        default="",
        help="Optional path to save final page screenshot for debugging.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retry attempts (default: 2).",
    )
    return parser.parse_args()


def _normalize_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _with_attempt_suffix(path_value: str, attempt_no: int, total_attempts: int) -> Path:
    p = Path(path_value)
    if total_attempts <= 1:
        return p
    stem = p.stem or "debug"
    suffix = p.suffix
    return p.with_name(f"{stem}.attempt{attempt_no}{suffix}")


def _click_first_visible(page: Any, selectors: list[str]) -> dict[str, Any]:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 8)
        except Exception:
            continue
        for idx in range(count):
            cand = locator.nth(idx)
            try:
                if cand.is_visible() and cand.is_enabled():
                    cand.click(timeout=2000)
                    return {"ok": True, "selector": selector, "index": idx}
            except Exception:
                continue
    return {"ok": False, "reason": "button_not_found"}


def _fill_and_submit_with_locators(page: Any, registration_number: str) -> dict[str, Any]:
    input_selectors = [
        "input[placeholder*='registration' i]",
        "input[aria-label*='registration' i]",
        "input[name*='registration' i]",
        "input[id*='registration' i]",
        "input[name*='reg' i]",
        "input[id*='reg' i]",
        "input[type='text']",
        "input:not([type])",
    ]
    button_selectors = [
        "button:has-text('Search')",
        "button:has-text('Submit')",
        "input[type='submit']",
        "button[type='submit']",
        "input[type='button'][value*='Search' i]",
        "input[type='button'][value*='Submit' i]",
    ]

    for selector in input_selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 8)
        except Exception:
            continue
        for idx in range(count):
            inp = locator.nth(idx)
            try:
                if not inp.is_visible() or not inp.is_enabled():
                    continue
                inp.click(timeout=1500)
                inp.fill("")
                inp.fill(registration_number)
                inp.dispatch_event("input")
                inp.dispatch_event("change")
                btn = _click_first_visible(page, button_selectors)
                if btn.get("ok"):
                    return {
                        "ok": True,
                        "method": "locator_fill_click",
                        "input_selector": selector,
                        "input_index": idx,
                        "button_selector": btn.get("selector"),
                    }
                try:
                    inp.press("Enter")
                    return {
                        "ok": True,
                        "method": "locator_fill_enter",
                        "input_selector": selector,
                        "input_index": idx,
                    }
                except Exception:
                    continue
            except Exception:
                continue
    return {"ok": False, "reason": "locator_input_not_found"}


def _fill_and_submit_with_dom_heuristic(page: Any, registration_number: str) -> dict[str, Any]:
    # DOM-side heuristics so minor markup changes do not break quickly.
    return page.evaluate(
        """
        (regNo) => {
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };

          const norm = (txt) => String(txt || '').toLowerCase().trim();
          const scoreInput = (el) => {
            const p = norm(el.getAttribute('placeholder'));
            const n = norm(el.getAttribute('name'));
            const i = norm(el.getAttribute('id'));
            const aria = norm(el.getAttribute('aria-label'));
            const nearby = norm((el.closest('form, section, div') || document.body).innerText).slice(0, 1200);
            let score = 0;
            if (p.includes('registration no')) score += 10;
            if (aria.includes('registration no')) score += 10;
            if (n.includes('registration') || i.includes('registration')) score += 8;
            if (n.includes('reg') || i.includes('reg')) score += 4;
            if (nearby.includes('browse by registration number')) score += 6;
            if (nearby.includes('registration no')) score += 3;
            return score;
          };

          const inputs = Array.from(document.querySelectorAll("input[type='text'], input:not([type])"))
            .filter((el) => isVisible(el) && !el.disabled && !el.readOnly);

          const ranked = inputs
            .map((el) => ({ el, score: scoreInput(el) }))
            .filter((x) => x.score > 0)
            .sort((a, b) => b.score - a.score);

          if (!ranked.length) {
            return { ok: false, reason: 'registration_input_not_found' };
          }

          const input = ranked[0].el;
          input.focus();
          input.value = regNo;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));

          const section = input.closest('form, section, div') || document.body;
          let button =
            section.querySelector("button[type='submit']") ||
            section.querySelector("input[type='submit']") ||
            Array.from(section.querySelectorAll("button, input[type='button']"))
              .find((b) => norm(b.innerText || b.value).includes('submit'));

          if (!button && input.form) {
            button = input.form.querySelector("button[type='submit'], input[type='submit']");
          }

          if (button && isVisible(button)) {
            button.click();
            return {
              ok: true,
              method: 'click_submit',
              input_hint: {
                placeholder: input.getAttribute('placeholder') || '',
                name: input.getAttribute('name') || '',
                id: input.getAttribute('id') || ''
              }
            };
          }

          input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
          input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
          return {
            ok: true,
            method: 'press_enter',
            input_hint: {
              placeholder: input.getAttribute('placeholder') || '',
              name: input.getAttribute('name') || '',
              id: input.getAttribute('id') || ''
            }
          };
        }
        """,
        registration_number,
    )


def _fill_and_submit_registration_number(page: Any, registration_number: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    locator_step = _fill_and_submit_with_locators(page, registration_number)
    steps.append({"strategy": "locator", "result": locator_step})
    if locator_step.get("ok"):
        return {"ok": True, "primary": locator_step, "steps": steps}

    dom_step = _fill_and_submit_with_dom_heuristic(page, registration_number)
    steps.append({"strategy": "dom_heuristic", "result": dom_step})
    if dom_step.get("ok"):
        return {"ok": True, "primary": dom_step, "steps": steps}

    return {"ok": False, "reason": "submit_failed", "steps": steps}


def _extract_visible_tables(page: Any, max_rows: int) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        (limitRows) => {
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };
          const clean = (txt) => String(txt || '').replace(/\\s+/g, ' ').trim();
          const tables = Array.from(document.querySelectorAll('table')).filter(isVisible);
          const out = [];
          for (const t of tables) {
            const rows = Array.from(t.querySelectorAll('tr')).filter(isVisible);
            if (!rows.length) continue;
            const headerCells = rows[0].querySelectorAll('th,td');
            const headers = Array.from(headerCells).map((c) => clean(c.innerText));
            const body = [];
            for (const r of rows.slice(1)) {
              const cols = Array.from(r.querySelectorAll('td,th')).map((c) => clean(c.innerText));
              if (!cols.length) continue;
              body.push(cols);
              if (body.length >= limitRows) break;
            }
            if (!body.length) continue;
            out.push({ headers, rows: body });
          }
          return out;
        }
        """,
        max_rows,
    )


def _extract_candidate_blocks(page: Any, max_blocks: int = 120) -> list[str]:
    return page.evaluate(
        """
        (maxBlocks) => {
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };
          const clean = (txt) => String(txt || '').replace(/\\s+/g, ' ').trim();
          const out = [];
          const seen = new Set();
          const nodes = Array.from(document.querySelectorAll('tr, li, p, td, div'));
          for (const n of nodes) {
            if (!isVisible(n)) continue;
            const txt = clean(n.innerText || '');
            if (txt.length < 4 || txt.length > 500) continue;
            const k = txt.toLowerCase();
            if (!(k.includes('reg') || k.includes('registration') || k.includes('doctor') || k.includes('imr'))) continue;
            if (seen.has(txt)) continue;
            seen.add(txt);
            out.push(txt);
            if (out.length >= maxBlocks) break;
          }
          return out;
        }
        """,
        max_blocks,
    )


def _extract_page_signals(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const text = (document.body && document.body.innerText) ? document.body.innerText : '';
          const compact = text.replace(/\\s+/g, ' ').trim();
          return {
            title: document.title || '',
            has_no_results_text:
              /no\\s+data|no\\s+record|no\\s+result|not\\s+found/i.test(compact),
            has_view_imr_details_text: /view\\s+imr\\s+details/i.test(compact),
            excerpt: compact.slice(0, 2000),
            url: window.location.href
          };
        }
        """
    )


def _wait_for_results(page: Any, timeout_ms: int) -> dict[str, Any]:
    start = time.monotonic()
    deadline = start + (max(timeout_ms, 1000) / 1000.0)
    snapshots: list[dict[str, Any]] = []
    last_signals: dict[str, Any] = {}

    while time.monotonic() < deadline:
        tables = _extract_visible_tables(page, 3)
        signals = _extract_page_signals(page)
        last_signals = signals
        snap = {
            "tables_found": len(tables),
            "has_no_results_text": bool(signals.get("has_no_results_text")),
            "has_view_imr_details_text": bool(signals.get("has_view_imr_details_text")),
            "url": str(signals.get("url") or ""),
        }
        snapshots.append(snap)
        if len(snapshots) > 8:
            snapshots = snapshots[-8:]
        if snap["tables_found"] > 0 or snap["has_no_results_text"] or snap["has_view_imr_details_text"]:
            return {
                "ready": True,
                "elapsed_ms": int((time.monotonic() - start) * 1000),
                "snapshots": snapshots,
                "signals": last_signals,
            }
        try:
            page.wait_for_timeout(700)
        except Exception:
            break

    return {
        "ready": False,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "snapshots": snapshots,
        "signals": last_signals,
    }


def main() -> int:
    args = _parse_args()
    reg_no = str(args.registration_number or "").strip()
    if not reg_no:
        print(json.dumps({"ok": False, "error": "registration number is required"}))
        return 2

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        _emit_json(
            {
                "ok": False,
                "error": "playwright_not_installed",
                "hint": "pip install playwright && playwright install chromium",
            }
        )
        return 3

    result: dict[str, Any] = {
        "ok": False,
        "registration_number": reg_no,
        "url": args.url,
    }
    reg_norm = _normalize_for_match(reg_no)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headful)
            total_attempts = max(int(args.retries or 1), 1)
            attempt_summaries: list[dict[str, Any]] = []
            best_payload: dict[str, Any] | None = None

            for attempt in range(1, total_attempts + 1):
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(args.timeout_ms)
                attempt_data: dict[str, Any] = {"attempt": attempt}
                try:
                    page.goto(args.url, wait_until="domcontentloaded")
                    submit_meta = _fill_and_submit_registration_number(page, reg_no)
                    attempt_data["submit_meta"] = submit_meta

                    try:
                        page.wait_for_load_state("networkidle", timeout=min(args.timeout_ms, 15000))
                    except PlaywrightTimeoutError:
                        pass

                    wait_meta = _wait_for_results(page, args.timeout_ms)
                    tables = _extract_visible_tables(page, args.max_rows)
                    signals = _extract_page_signals(page)
                    blocks = _extract_candidate_blocks(page)

                    matched_rows: list[dict[str, Any]] = []
                    for table in tables:
                        headers = table.get("headers") or []
                        for row in table.get("rows") or []:
                            row_text = _normalize_for_match(" | ".join(str(x) for x in row))
                            if reg_norm and reg_norm in row_text:
                                matched_rows.append({"headers": headers, "row": row})

                    matched_blocks = [b for b in blocks if reg_norm and reg_norm in _normalize_for_match(b)]

                    lookup_status = "inconclusive"
                    if matched_rows or matched_blocks:
                        lookup_status = "match_found"
                    elif signals.get("has_no_results_text"):
                        lookup_status = "not_found"

                    payload = {
                        "ok": True,
                        "registration_number": reg_no,
                        "lookup_status": lookup_status,
                        "submit_meta": submit_meta,
                        "wait_meta": wait_meta,
                        "page_signals": signals,
                        "tables_found": len(tables),
                        "matched_rows_count": len(matched_rows),
                        "matched_rows": matched_rows,
                        "matched_blocks_count": len(matched_blocks),
                        "matched_blocks": matched_blocks[:20],
                        "tables_sample": tables[:5],
                    }

                    if args.save_html:
                        html_path = _with_attempt_suffix(args.save_html, attempt, total_attempts)
                        html_path.parent.mkdir(parents=True, exist_ok=True)
                        html_path.write_text(page.content(), encoding="utf-8")
                        payload["saved_html"] = str(html_path)
                    if args.save_screenshot:
                        shot_path = _with_attempt_suffix(args.save_screenshot, attempt, total_attempts)
                        shot_path.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(shot_path), full_page=True)
                        payload["saved_screenshot"] = str(shot_path)

                    attempt_data["lookup_status"] = lookup_status
                    attempt_data["matched_rows_count"] = len(matched_rows)
                    attempt_data["matched_blocks_count"] = len(matched_blocks)
                    attempt_summaries.append(attempt_data)

                    if best_payload is None:
                        best_payload = payload
                    else:
                        best_score = int(best_payload.get("matched_rows_count", 0)) * 100 + int(
                            best_payload.get("matched_blocks_count", 0)
                        )
                        cur_score = int(payload.get("matched_rows_count", 0)) * 100 + int(
                            payload.get("matched_blocks_count", 0)
                        )
                        if cur_score > best_score:
                            best_payload = payload

                    if lookup_status in {"match_found", "not_found"}:
                        break
                except Exception as exc:
                    attempt_data["error"] = str(exc)
                    attempt_summaries.append(attempt_data)
                finally:
                    context.close()

            browser.close()

            if best_payload is not None:
                best_payload["attempts"] = attempt_summaries
                result = best_payload
            else:
                result.update(
                    {
                        "ok": False,
                        "error": "all_attempts_failed",
                        "attempts": attempt_summaries,
                    }
                )
    except Exception as exc:
        result.update({"ok": False, "error": str(exc)})
        _emit_json(result)
        return 1

    _emit_json(result, pretty=True)
    return 0


def _emit_json(payload: dict[str, Any], pretty: bool = False) -> None:
    text = json.dumps(payload, ensure_ascii=True, indent=2 if pretty else None)
    # Use binary write to avoid Windows console encoding failures.
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
