(()=>{
  const pageNames={dashboard:'Dashboard',pdv:'PDV / Venda',estoque:'Produtos & Estoque',movimentos:'Entradas & Saídas',relatorios:'Relatórios'};
  const icon=(name)=>({
    dashboard:'<svg viewBox="0 0 24 24"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg>',
    pdv:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M9 12h6M12 9v6"/></svg>',
    estoque:'<svg viewBox="0 0 24 24"><path d="M4 7l8-4 8 4-8 4zM4 7v10l8 4 8-4V7M12 11v10"/></svg>',
    movimentos:'<svg viewBox="0 0 24 24"><path d="M7 7h11l-3-3M17 17H6l3 3M18 7l-3 3M6 17l3-3"/></svg>',
    compras:'<svg viewBox="0 0 24 24"><path d="M6 7h14l-1.5 8h-11zM6 7L5 3H2M9 20h.01M17 20h.01"/></svg>'
  }[name]||'');

  function cleanStatus(){
    const status=document.getElementById('status');
    if(!status)return;
    status.textContent=status.textContent.replace(/^\s*●\s*/,'').trim()||'Online';
  }

  function arrangeTop(){
    const top=document.querySelector('.app main>.top');
    if(!top)return;
    let right=top.querySelector('.at-top-right');
    if(!right){right=document.createElement('div');right.className='at-top-right';top.appendChild(right)}
    const clock=top.querySelector('.at-clock');
    const status=document.getElementById('status');
    if(clock&&clock.parentElement!==right)right.appendChild(clock);
    if(status&&status.parentElement!==right)right.appendChild(status);
  }

  function fixTitles(){
    const nav=document.getElementById('nav');
    const title=document.getElementById('title');
    if(!nav||!title)return;
    const set=(key)=>{if(pageNames[key])title.textContent=pageNames[key]};
    nav.addEventListener('click',e=>{
      const b=e.target.closest('button[data-page]');if(!b)return;
      setTimeout(()=>set(b.dataset.page),0);
    });
    const active=nav.querySelector('button.active[data-page]');if(active)set(active.dataset.page);
  }

  function handleHash(){
    const key=(location.hash||'').replace('#','');
    if(!pageNames[key])return;
    const b=document.querySelector(`#nav button[data-page="${key}"]`);
    if(b)setTimeout(()=>b.click(),20);
  }

  function classifyAlerts(){
    document.querySelectorAll('#alerts p').forEach(p=>{
      p.classList.remove('at-alert-min','at-alert-critical');
      const m=p.textContent.match(/(\d+)\s*un\.\s*•\s*mínimo\s*(\d+)/i);
      if(!m)return;
      const stock=Number(m[1]),min=Number(m[2]);
      p.classList.add(stock<min?'at-alert-critical':'at-alert-min');
    });
    const alerts=document.getElementById('alerts');
    if(alerts)new MutationObserver(classifyAlerts).observe(alerts,{childList:true,subtree:true});
  }

  function standaloneShell(){
    if(document.querySelector('.app')||document.querySelector('.at-standalone-sidebar'))return;
    const main=document.querySelector('main');if(!main)return;
    const path=location.pathname.toLowerCase();
    const current=path.includes('movimentacoes')?'movimentos':path.includes('compras')?'compras':path.includes('editar-produtos')?'estoque':'';
    if(!current)return;
    document.body.classList.add('at-standalone-with-shell');
    const aside=document.createElement('aside');aside.className='at-standalone-sidebar';
    const links=[
      ['dashboard','/','Dashboard'],
      ['pdv','/#pdv','PDV / Venda'],
      ['estoque','/#estoque','Produtos'],
      ['movimentos','/movimentacoes.html','Entradas & Saídas'],
      ['compras','/compras.html','Compras / NF-e']
    ];
    aside.innerHTML=`<div class="at-standalone-brand"><span class="mark">AT</span><span>ADEGA <b>TORRES</b></span></div><nav class="at-standalone-nav">${links.map(([k,href,label])=>`<a href="${href}" class="${current===k?'active':''}">${icon(k)}<span>${label}</span></a>`).join('')}</nav><div class="at-standalone-footer"><strong>Adega Torres</strong>Operação integrada • PostgreSQL</div>`;
    document.body.prepend(aside);
  }

  function improveCartBadge(){
    const badge=document.querySelector('.at-cart-badge');if(!badge)return;
    badge.setAttribute('aria-label','Itens diferentes no carrinho');
    if(badge.textContent.trim()==='0')badge.hidden=true;
  }

  function observeDynamic(){
    const app=document.querySelector('.app');
    if(!app)return;
    new MutationObserver(()=>{cleanStatus();arrangeTop();improveCartBadge()}).observe(app,{childList:true,subtree:true,characterData:true});
  }

  function init(){
    cleanStatus();arrangeTop();fixTitles();handleHash();classifyAlerts();standaloneShell();improveCartBadge();observeDynamic();
    document.documentElement.classList.add('premium-v2-ready');
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
