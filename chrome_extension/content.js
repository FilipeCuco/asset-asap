(function() {
  'use strict';

  const SERVER_URL = 'http://127.0.0.1:7890/import-asset';

  // Injeta a fonte Inter Variable
  const fontStyle = document.createElement('style');
  fontStyle.textContent = `
    @font-face {
      font-family: 'Inter Variable';
      src: url('https://rsms.me/inter/font-files/InterVariable.woff2?v=4.1') format('woff2');
      font-weight: 100 900;
      font-display: swap;
      font-style: normal;
    }
  `;
  document.head.appendChild(fontStyle);

  function isValidAssetName(name) {
    if (!name || name.length < 3) return false;
    const regex = /^[a-zA-Z0-9_$!]+$/;
    return regex.test(name) && !['OBJECTS', 'CLOTHES', 'VEHICLES', 'FAVORITES'].includes(name.toUpperCase());
  }

  function extractName(el, fallbackUrl = false) {
    let text = "";
    if (el) {
      text = el.innerText || el.textContent || "";
    } else if (fallbackUrl) {
      const parts = window.location.pathname.split('/').filter(p => p.length > 0);
      text = parts[parts.length - 1] || "";
    }
    const clean = text.replace(/Name:|Model:|Copy|Name|Model|/gi, '').trim().split('\n')[0].trim();
    return isValidAssetName(clean) ? clean : null;
  }

  async function sendToBlender(btn, name) {
    const originalContent = btn.innerHTML;
    btn.innerHTML = '<span>...</span>';
    btn.style.opacity = '0.9';

    try {
      const response = await fetch(SERVER_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        mode: 'cors',
        body: JSON.stringify({ asset_name: name })
      });

      if (response.ok) {
        btn.innerHTML = '<span>✔</span>';
        btn.style.backgroundColor = '#4CAF50';
      } else {
        btn.innerHTML = '<span>✘</span>';
        btn.style.backgroundColor = '#F44336';
      }
    } catch (e) {
      btn.innerHTML = '<span>!</span>';
      btn.style.backgroundColor = '#757575';
    } finally {
      setTimeout(() => {
        btn.innerHTML = originalContent;
        btn.style.opacity = '1';
        btn.style.backgroundColor = btn.dataset.originalBg || 'rgba(33, 150, 243, 0.95)';
      }, 2000);
    }
  }

  function applyNativeStyle(b, isList = false) {
    const style = {
      backgroundColor: isList ? 'rgba(33, 150, 243, 0.95)' : '#2196F3',
      color: '#FFFFFF',
      border: 'none',
      borderRadius: '4px',
      cursor: 'pointer',
      fontWeight: '700',
      textTransform: 'uppercase',
      fontSize: isList ? '10px' : '14px',
      padding: '0',
      height: isList ? '24px' : '44px',
      width: isList ? '48px' : 'auto',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      lineHeight: '1',
      letterSpacing: 'normal',
      transition: 'all 0.15s ease',
      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
      zIndex: '20',
      fontFamily: '"Inter Variable", sans-serif',
      fontFeatureSettings: '"cv02", "cv05", "cv08"',
      backdropFilter: isList ? 'blur(4px)' : 'none',
      margin: '0'
    };

    if (isList) {
      style.position = 'absolute';
      style.bottom = '8px';
      style.right = '8px';
    }

    Object.assign(b.style, style);
    b.dataset.originalBg = style.backgroundColor;
    
    b.onmouseover = () => { if(!b.disabled) b.style.transform = 'scale(1.05)'; };
    b.onmouseout = () => { if(!b.disabled) b.style.transform = 'scale(1)'; };
  }

  function inject() {
    // 1. Botão na página interna
    if (!document.getElementById('asap-main-btn')) {
      const buttons = Array.from(document.querySelectorAll('button, a, .v-btn'));
      const ref = buttons.find(b => {
        const t = (b.innerText || "").toUpperCase();
        return t.includes('DOWNLOAD POSITIONS') || t.includes('DOWNLOAD XML');
      });

      if (ref && ref.parentNode) {
        const name = extractName(null, true);
        if (name) {
          const mainBtn = document.createElement('button');
          mainBtn.id = 'asap-main-btn';
          mainBtn.innerHTML = '<span>SEND TO BLENDER</span>';
          applyNativeStyle(mainBtn, false);
          mainBtn.style.width = '100%';
          mainBtn.style.marginTop = '16px';
          mainBtn.onclick = (e) => { e.preventDefault(); e.stopPropagation(); sendToBlender(mainBtn, name); };
          ref.parentNode.insertBefore(mainBtn, ref.nextSibling);
        }
      }
    }

    // 2. Botão nos cards
    const cards = document.querySelectorAll('.v-card, .v-list-item');
    cards.forEach(card => {
      if (card.querySelector('.asap-list-btn')) return;

      const nameEl = card.querySelector('b, .v-card__title, .v-list-item__title, .v-card-title, .text-h6');
      if (!nameEl) return;

      const name = extractName(nameEl);
      if (!name) return;

      const imgContainer = card.querySelector('.v-img, .v-responsive, .v-card__image') || card;

      const listBtn = document.createElement('button');
      listBtn.className = 'asap-list-btn';
      listBtn.innerHTML = '<span>SEND</span>';
      applyNativeStyle(listBtn, true);
      
      listBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        sendToBlender(listBtn, name);
      };

      if (getComputedStyle(imgContainer).position === 'static') {
        imgContainer.style.position = 'relative';
      }
      imgContainer.appendChild(listBtn);
    });
  }

  setInterval(inject, 1200);
  inject();
})();
