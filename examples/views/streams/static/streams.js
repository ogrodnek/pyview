// Streams Demo - Diff Viewer Hook
// This hook intercepts websocket messages and displays them in the diff viewer panel

window.Hooks = window.Hooks ?? {};

// Store for diff entries
let diffEntries = [];
const MAX_ENTRIES = 50;

// Clear diffs function (exposed globally for the clear button)
window.clearDiffs = function() {
  diffEntries = [];
  renderDiffs();
};

// Render the diff log
function renderDiffs() {
  const container = document.getElementById('diff-log');
  if (!container) return;

  if (diffEntries.length === 0) {
    container.innerHTML = '<div class="text-gray-500 italic">Waiting for diffs...</div>';
    return;
  }

  container.innerHTML = diffEntries.map((entry, index) => {
    const hasStream = JSON.stringify(entry.diff).includes('"stream"');
    const borderColor = hasStream ? 'border-green-500' : 'border-gray-600';
    const label = hasStream ?
      '<span class="text-green-400 text-xs font-semibold">STREAM</span>' :
      '<span class="text-gray-500 text-xs">DIFF</span>';

    return `
      <div class="border-l-2 ${borderColor} pl-3 pb-3">
        <div class="flex items-center gap-2 mb-1">
          ${label}
          <span class="text-gray-500 text-xs">${entry.timestamp}</span>
        </div>
        <pre class="text-gray-300 text-xs overflow-x-auto whitespace-pre-wrap">${syntaxHighlight(entry.diff)}</pre>
      </div>
    `;
  }).join('');

  // Scroll to bottom
  container.scrollTop = container.scrollHeight;
}

// Syntax highlight JSON for readability
function syntaxHighlight(json) {
  const str = JSON.stringify(json, null, 2);
  return str.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
    let cls = 'text-orange-300'; // number
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        // Key
        if (match.includes('"stream"') || match.includes('"d"') || match.includes('"s"')) {
          cls = 'text-green-400 font-semibold'; // special keys
        } else {
          cls = 'text-blue-400'; // regular key
        }
      } else {
        cls = 'text-yellow-300'; // string value
      }
    } else if (/true|false/.test(match)) {
      cls = 'text-purple-400'; // boolean
    } else if (/null/.test(match)) {
      cls = 'text-gray-500'; // null
    }
    return '<span class="' + cls + '">' + match + '</span>';
  });
}

// Hook into the LiveSocket to capture messages
function setupMessageInterceptor() {
  // Wait for liveSocket to be available
  if (!window.liveSocket) {
    setTimeout(setupMessageInterceptor, 100);
    return;
  }

  const socket = window.liveSocket;

  // Get the Phoenix socket channel
  // We need to intercept at the channel level
  const originalOnMessage = socket.socket.onMessage;

  socket.socket.onMessage = function(rawMessage) {
    try {
      // Parse the message - Phoenix uses a specific format
      // [join_ref, ref, topic, event, payload]
      const data = JSON.parse(rawMessage.data);

      if (Array.isArray(data) && data.length >= 5) {
        const [joinRef, ref, topic, event, payload] = data;

        // Only capture diff events for our topic
        if (event === 'diff' && payload && Object.keys(payload).length > 0) {
          const timestamp = new Date().toLocaleTimeString();

          diffEntries.unshift({
            timestamp,
            event,
            topic,
            diff: payload
          });

          // Limit entries
          if (diffEntries.length > MAX_ENTRIES) {
            diffEntries = diffEntries.slice(0, MAX_ENTRIES);
          }

          renderDiffs();
        }
      }
    } catch (e) {
      // Ignore parse errors for non-JSON messages
    }

    // Call original handler
    return originalOnMessage.call(this, rawMessage);
  };

  console.log('Diff viewer interceptor installed');
}

window.Hooks.DiffViewer = {
  mounted() {
    setupMessageInterceptor();
    renderDiffs();
  },

  updated() {
    // Re-render on updates (though this hook element doesn't change)
  }
};
