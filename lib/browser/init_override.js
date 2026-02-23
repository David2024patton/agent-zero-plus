// Open all shadow DOMs so the browser agent can see web component internals
(function () {
  const originalAttachShadow = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function attachShadow(options) {
    return originalAttachShadow.call(this, { ...options, mode: "open" });
  };
})();

// Iframe content extraction bridge
// Enables the browser agent to read content from cross-origin iframes
// by using postMessage communication
(function () {
  let elementCounter = 0;
  const ignoredTags = [
    "style",
    "script",
    "meta",
    "link",
    "svg",
    "noscript",
    "path",
  ];

  function isElementVisible(element) {
    if (element.nodeType !== Node.ELEMENT_NODE) {
      return true;
    }

    const computedStyle = window.getComputedStyle(element);

    if (
      computedStyle.display === "none" ||
      computedStyle.visibility === "hidden" ||
      computedStyle.opacity === "0"
    ) {
      return false;
    }

    if (element.tagName === "INPUT" && element.type === "hidden") {
      return false;
    }

    if (
      element.hasAttribute("hidden") ||
      element.getAttribute("aria-hidden") === "true"
    ) {
      return false;
    }

    return true;
  }

  function convertAttribute(tag, attr) {
    let out = {
      name: attr.name,
      value: attr.value,
    };

    if (["srcset"].includes(out.name)) return null;
    if (out.name.startsWith("data-") && out.name != "data-A0UID" && out.name != "data-a0-frame-id") return null;

    if (tag === "img" && out.value.startsWith("data:")) out.value = "data...";

    return out;
  }

  // Extract DOM content from the current frame
  window.__A0_extractFrameContent = function () {
    const extractContent = (node) => {
      if (!node) return "";

      let content = "";
      const tagName = node.tagName ? node.tagName.toLowerCase() : "";

      if (tagName && ignoredTags.includes(tagName)) {
        return "";
      }

      if (node.nodeType === Node.ELEMENT_NODE) {
        if (tagName) {
          const uid = elementCounter++;
          node.setAttribute("data-A0UID", uid);
        }

        content += `<${tagName}`;

        if (!isElementVisible(node)) {
          content += " invisible";
        }

        for (let attr of node.attributes) {
          const out = convertAttribute(tagName, attr);
          if (out) content += ` ${out.name}="${out.value}"`;
        }

        if (tagName) {
          content += ` selector="${node.getAttribute("data-A0UID")}"`;
        }

        content += ">";

        // Handle shadow DOM
        if (node.shadowRoot) {
          content += "<!-- Shadow DOM Start -->";
          for (let shadowChild of node.shadowRoot.childNodes) {
            content += extractContent(shadowChild);
          }
          content += "<!-- Shadow DOM End -->";
        }

        // Handle child nodes
        for (let child of node.childNodes) {
          content += extractContent(child);
        }

        content += `</${tagName}>`;
      } else if (node.nodeType === Node.TEXT_NODE) {
        content += node.textContent;
      } else if (node.nodeType === Node.COMMENT_NODE) {
        content += `<!--${node.textContent}-->`;
      }

      return content;
    };

    return extractContent(document.documentElement);
  };

  // Listen for content extraction requests from parent frames
  window.addEventListener('message', function (event) {
    if (event.data === 'A0_REQUEST_CONTENT') {
      const content = window.__A0_extractFrameContent();
      window.parent.postMessage({
        type: 'A0_FRAME_CONTENT',
        content: content,
        frameId: window.frameElement?.getAttribute('data-a0-frame-id')
      }, '*');
    }
  });

  // Extract content from all frames in the page
  window.__A0_extractAllFramesContent = async function (rootNode = document) {
    let content = "";

    content += window.__A0_extractFrameContent();

    const iframes = rootNode.getElementsByTagName('iframe');
    const frameContents = new Map();

    const framePromises = Array.from(iframes).map((iframe) => {
      return new Promise((resolve) => {
        const frameId = 'frame_' + Math.random().toString(36).substr(2, 9);
        iframe.setAttribute('data-a0-frame-id', frameId);

        const listener = function (event) {
          if (event.data?.type === 'A0_FRAME_CONTENT' &&
            event.data?.frameId === frameId) {
            frameContents.set(frameId, event.data.content);
            window.removeEventListener('message', listener);
            resolve();
          }
        };
        window.addEventListener('message', listener);

        try {
          iframe.contentWindow.postMessage('A0_REQUEST_CONTENT', '*');
        } catch (e) {
          // Cross-origin iframe, can't communicate
          resolve();
          return;
        }

        // Timeout after 2 seconds
        setTimeout(resolve, 2000);
      });
    });

    await Promise.all(framePromises);

    for (let iframe of iframes) {
      const frameId = iframe.getAttribute('data-a0-frame-id');
      const frameContent = frameContents.get(frameId);
      if (frameContent) {
        content += `<!-- IFrame ${iframe.src || 'unnamed'} Content Start -->`;
        content += frameContent;
        content += `<!-- IFrame Content End -->`;
      }
    }

    return content;
  };
})();