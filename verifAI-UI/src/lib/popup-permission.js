/**
 * Popup Permission Helper
 * 
 * Provides utilities to detect popup blocking, request permission,
 * and guide users on enabling popups for the application.
 */

/**
 * Test if the browser allows popups
 * @returns {boolean} true if popups are allowed
 */
export function isPopupAllowed() {
  const testPopup = window.open("", "_blank", "noopener,noreferrer");
  if (!testPopup) {
    return false;
  }
  testPopup.close();
  return true;
}

/**
 * Open a URL in a new tab with popup blocking detection
 * @param {string} url - The URL to open
 * @param {Object} options - Options object
 * @param {string} [options.windowFeatures] - Window features string for window.open
 * @param {boolean} [options.fallbackToSameTab=true] - If popup blocked, navigate in same tab
 * @returns {Window|null} The opened window object or null if blocked
 */
export function openInNewTab(url, { windowFeatures = "noopener,noreferrer", fallbackToSameTab = true } = {}) {
  try {
    const popup = window.open(url, "_blank", windowFeatures);
    
    if (!popup) {
      // Popup blocked by browser
      if (fallbackToSameTab) {
        window.location.href = url;
        return null;
      }
      return null;
    }

    // Check if popup was actually blocked (some browsers return object but block)
    popup.onload = () => {
      try {
        // Try to access popup.location - if blocked, this will throw
        const _loc = popup.location;
      } catch (err) {
        // Popup is blocked but window.open returned an object
        if (fallbackToSameTab) {
          window.location.href = url;
        }
      }
    };

    return popup;
  } catch (err) {
    // window.open itself failed
    if (fallbackToSameTab) {
      window.location.href = url;
    }
    return null;
  }
}

/**
 * Get browser-specific instructions for enabling popups
 * @returns {string} HTML string with instructions
 */
export function getPopupEnableInstructions() {
  const userAgent = navigator.userAgent;
  
  // Detect browser
  const isChrome = /Chrome/.test(userAgent) && /Google Inc/.test(navigator.vendor);
  const isFirefox = /Firefox/.test(userAgent);
  const isSafari = /^((?!chrome|android).)*safari/i.test(userAgent);
  const isEdge = /Edg/.test(userAgent);
  
  if (isChrome || isEdge) {
    return `
      <ol style="text-align: left; margin-left: 20px;">
        <li>Look for the <strong>popup blocked icon</strong> (🚫) in the address bar (right side)</li>
        <li>Click on it and select <strong>"Always allow popups from ${window.location.hostname}"</strong></li>
        <li>Click <strong>"Done"</strong></li>
        <li>Click the button again to open the document</li>
      </ol>
    `;
  } else if (isFirefox) {
    return `
      <ol style="text-align: left; margin-left: 20px;">
        <li>Look for the <strong>popup notification bar</strong> at the top of the browser</li>
        <li>Click <strong>"Options"</strong> and select <strong>"Always allow popups from ${window.location.hostname}"</strong></li>
        <li>Click <strong>"Allow"</strong></li>
        <li>Click the button again to open the document</li>
      </ol>
    `;
  } else if (isSafari) {
    return `
      <ol style="text-align: left; margin-left: 20px;">
        <li>Go to <strong>Safari</strong> → <strong>Preferences</strong> (or press ⌘+,)</li>
        <li>Click on the <strong>"Websites"</strong> tab</li>
        <li>Select <strong>"Pop-up Windows"</strong> from the left sidebar</li>
        <li>Find <strong>${window.location.hostname}</strong> and set it to <strong>"Allow"</strong></li>
        <li>Refresh the page and try again</li>
      </ol>
    `;
  } else {
    return `
      <ol style="text-align: left; margin-left: 20px;">
        <li>Look for a <strong>popup blocked notification</strong> in your browser's address bar</li>
        <li>Click on it and choose <strong>"Always allow popups from ${window.location.hostname}"</strong></li>
        <li>Refresh the page if needed</li>
        <li>Click the button again to open the document</li>
      </ol>
    `;
  }
}

/**
 * Request popup permission by opening a test popup with a message
 * @returns {boolean} true if popup was successful, false if blocked
 */
export function requestPopupPermission() {
  const testPopup = window.open("", "_blank", "width=400,height=300,noopener,noreferrer");
  
  if (!testPopup) {
    return false;
  }
  
  try {
    testPopup.document.write(`
      <!DOCTYPE html>
      <html>
        <head><title>Popup Permission Granted</title></head>
        <body style="font-family: system-ui, sans-serif; padding: 20px; text-align: center;">
          <h2 style="color: #10b981;">✓ Popup Allowed!</h2>
          <p>You can close this window and return to the application.</p>
          <p style="color: #6b7280; font-size: 14px;">This popup confirms that popups are enabled for this site.</p>
        </body>
      </html>
    `);
    testPopup.document.close();
    return true;
  } catch (err) {
    return false;
  }
}
