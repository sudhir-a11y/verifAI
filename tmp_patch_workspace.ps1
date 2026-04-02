 = 'c:\QC-Python\app\web\qc\public\workspace.js'
 = Get-Content -Raw 
 = if (.Contains("
")) { "
" } else { "
" }

if ( -notmatch 'completedReportsMessageHandler') {
   = '  const headerActions = document.getElementById("header-actions");'
   = @'
  let completedReportsMessageHandler = null;

  function detachCompletedReportsMessageListener() {
    if (!completedReportsMessageHandler) return;
    window.removeEventListener('message', completedReportsMessageHandler);
    completedReportsMessageHandler = null;
  }
'@
   =  -replace "
", 
   = .Replace(,  +  + .TrimEnd())
}

 = .Replace(
  "const popup = window.open(url, '_blank', 'noopener,width=1500,height=900');",
  "const popup = window.open(url, '_blank', 'width=1500,height=900,resizable=yes,scrollbars=yes');"
)

if ( -notmatch 'qc-updated') {
   = @'
    detachCompletedReportsMessageListener();
    completedReportsMessageHandler = async function (event) {
      try {
        if (!event || event.origin !== window.location.origin) return;
        const payload = (event.data && typeof event.data === 'object') ? event.data : null;
        if (!payload || payload.type !== 'qc-updated') return;
        await loadRows(false);
      } catch (_err) {
      }
    };
    window.addEventListener('message', completedReportsMessageHandler);

'@
   =  -replace "
", 
   = '    try {' +  + '      await loadRows(true);'
   = .LastIndexOf()
  if ( -ge 0) {
     = .Insert(, )
  }
}

if ( -notmatch 'async function renderPage\(activeRole, page\) \{\s*detachCompletedReportsMessageListener\(\);') {
   = .Replace(
    'async function renderPage(activeRole, page) {',
    'async function renderPage(activeRole, page) {' +  + '    detachCompletedReportsMessageListener();'
  )
}

Set-Content -Path  -Value 
