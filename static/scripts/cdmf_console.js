// cdmf_console.js - Server console and application control

(function() {
  'use strict';

  // Console state
  let eventSource = null;
  let consoleExpanded = false;
  const MAX_CONSOLE_LINES = 500;

  // Initialize console on page load
  function initConsole() {
    const consoleOutput = document.getElementById('consoleOutput');
    const consolePanel = document.getElementById('consolePanel');
    const exitBtn = document.getElementById('btnExitApp');

    if (!consoleOutput) {
      console.warn('[Console] Console output element not found');
      return;
    }

    // Start streaming logs
    connectLogStream();

    // Set up exit button
    if (exitBtn) {
      exitBtn.addEventListener('click', handleExitApp);
    }
  }

  // Connect to log streaming endpoint using Server-Sent Events
  function connectLogStream() {
    const consoleOutput = document.getElementById('consoleOutput');
    if (!consoleOutput) return;

    try {
      // Close existing connection if any
      if (eventSource) {
        eventSource.close();
      }

      // Connect to SSE endpoint
      eventSource = new EventSource('/logs/stream');

      eventSource.onmessage = function(event) {
        appendLogLine(event.data);
      };

      eventSource.onerror = function(error) {
        console.error('[Console] Log stream error:', error);
        appendLogLine('[System] Log stream disconnected. Reconnecting...');
        
        // Attempt to reconnect after a delay
        setTimeout(() => {
          if (eventSource.readyState === EventSource.CLOSED) {
            connectLogStream();
          }
        }, 5000);
      };

      eventSource.onopen = function() {
        console.log('[Console] Log stream connected');
      };

    } catch (error) {
      console.error('[Console] Failed to connect to log stream:', error);
      appendLogLine('[System] Failed to connect to log stream: ' + error.message);
    }
  }

  // Append a line to the console output
  function appendLogLine(line) {
    const consoleOutput = document.getElementById('consoleOutput');
    if (!consoleOutput) return;

    // Create a text node for the new line
    const lineText = document.createTextNode(line + '\n');
    consoleOutput.appendChild(lineText);

    // Efficiently trim old lines by counting child nodes
    // Each line is a text node, so count them
    const textNodes = [];
    for (let node of consoleOutput.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        textNodes.push(node);
      }
    }

    // Remove old nodes if we exceed max lines
    if (textNodes.length > MAX_CONSOLE_LINES) {
      const nodesToRemove = textNodes.length - MAX_CONSOLE_LINES;
      for (let i = 0; i < nodesToRemove; i++) {
        consoleOutput.removeChild(textNodes[i]);
      }
    }

    // Auto-scroll to bottom if already near bottom
    const scrolledToBottom = consoleOutput.scrollHeight - consoleOutput.clientHeight <= consoleOutput.scrollTop + 50;
    if (scrolledToBottom || !consoleExpanded) {
      consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }
  }

  // Toggle console visibility
  function toggleConsole() {
    const consolePanel = document.getElementById('consolePanel');
    const toggleIcon = document.getElementById('consoleToggleIcon');
    
    if (!consolePanel || !toggleIcon) return;

    consoleExpanded = !consoleExpanded;

    if (consoleExpanded) {
      consolePanel.style.display = 'block';
      toggleIcon.classList.add('expanded');
      // Scroll to bottom when opening
      const consoleOutput = document.getElementById('consoleOutput');
      if (consoleOutput) {
        setTimeout(() => {
          consoleOutput.scrollTop = consoleOutput.scrollHeight;
        }, 100);
      }
    } else {
      consolePanel.style.display = 'none';
      toggleIcon.classList.remove('expanded');
    }
  }

  // Handle exit application button
  async function handleExitApp() {
    if (!confirm('Are you sure you want to exit AceForge?\n\nThis will stop the server and close the application.')) {
      return;
    }

    const exitBtn = document.getElementById('btnExitApp');
    if (exitBtn) {
      exitBtn.disabled = true;
      exitBtn.innerHTML = '<span class="icon">⏳</span><span class="label">Exiting...</span>';
    }

    try {
      const response = await fetch('/shutdown', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        // Show goodbye message
        document.body.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;">
            <div>
              <h1 style="font-size:3rem;margin-bottom:1rem;">👋</h1>
              <h2 style="color:#e5e7eb;margin-bottom:0.5rem;">AceForge has been stopped</h2>
              <p style="color:#9ca3af;">You can now close this browser tab and the terminal window.</p>
            </div>
          </div>
        `;

        // Close event source
        if (eventSource) {
          eventSource.close();
        }
      } else {
        alert('Failed to shutdown server. Please close the terminal window manually.');
        if (exitBtn) {
          exitBtn.disabled = false;
          exitBtn.innerHTML = '<span class="icon">🚪</span><span class="label">Exit</span>';
        }
      }
    } catch (error) {
      console.error('[Console] Shutdown error:', error);
      // Server might have already shut down, show goodbye anyway
      document.body.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;">
          <div>
            <h1 style="font-size:3rem;margin-bottom:1rem;">👋</h1>
            <h2 style="color:#e5e7eb;margin-bottom:0.5rem;">AceForge is stopping</h2>
            <p style="color:#9ca3af;">You can now close this browser tab and the terminal window.</p>
          </div>
        </div>
      `;

      if (eventSource) {
        eventSource.close();
      }
    }
  }

  // Expose functions to global CDMF object
  window.CDMF = window.CDMF || {};
  window.CDMF.toggleConsole = toggleConsole;
  window.CDMF.initConsole = initConsole;

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConsole);
  } else {
    initConsole();
  }

})();
