(()=>{
  const pageNames={dashboard:'Dashboard',pdv:'PDV / Venda',estoque:'Produtos & Estoque',movimentos:'Entradas & Saídas',relatorios:'Relatórios'};
  const icon=(name)=>({
    dashboard:'<svg viewBox="0 0 24 24"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg>',
    pdv:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M9 12h6M12 9v6"/></svg>',
    estoque:'<svg viewBox="0 0 24 24"><path d="M4 7l8-4 8 4-8 4zM4 7v10l8 4 8-4V7M12 11v10"/></svg>',
    movimentos:'<svg viewBox="0 0 24 24"><path d="M7 7h11l-3-3M17 17H6l3 3M18 7l-3 3M6 17l3-3"/></svg>',
    compras:'<svg viewBox="0 0 24 24"><path d="M6 7h14l-1.5 8h-11zM6 7L5 3H2M9 20h.01M17 20h.01"/></svg>'
    ,admin:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.7-.8-1.8.9-1.9-2.2-2.2-1.9.9-1.8-.8-.7-2h-3l-.7 2-1.8.8-1.9-.9-2.2 2.2.9 1.9-.8 1.8-2 .7v3l2 .7.8 1.8-.9 1.9 2.2 2.2 1.9-.9 1.8.8.7 2h3l.7-2 1.8-.8 1.9.9 2.2-2.2-.9-1.9.8-1.8z"/></svg>',
    cash:'<svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M7 6V4h10v2M7 11h4M16 14h.01"/></svg>',
    transfer:'<svg viewBox="0 0 24 24"><path d="M4 8h14l-3-3M20 16H6l3 3M18 8l-3 3M6 16l3-3"/></svg>'
  }[name]||'');

  function cleanStatus(){
    const status=document.getElementById('status');if(!status)return;
    const clean=status.textContent.replace(/^\s*●\s*/,'').trim()||'Online';
    if(status.textContent!==clean)status.textContent=clean;
  }

  function arrangeTop(){
    const top=document.querySelector('.app main>.top');if(!top)return;
    let right=top.querySelector('.at-top-right');
    if(!right){right=document.createElement('div');right.className='at-top-right';top.appendChild(right)}
    const clock=top.querySelector('.at-clock'),status=document.getElementById('status');
    if(clock&&clock.parentElement!==right)right.appendChild(clock);
    if(status&&status.parentElement!==right)right.appendChild(status);
  }

  function fixTitles(){
    const nav=document.getElementById('nav'),title=document.getElementById('title');if(!nav||!title)return;
    const set=key=>{if(pageNames[key]&&title.textContent!==pageNames[key])title.textContent=pageNames[key]};
    nav.addEventListener('click',e=>{const b=e.target.closest('button[data-page]');if(b)setTimeout(()=>set(b.dataset.page),0)});
    const active=nav.querySelector('button.active[data-page]');if(active)set(active.dataset.page);
  }

  function handleHash(){
    const key=(location.hash||'').replace('#','');if(!pageNames[key])return;
    const b=document.querySelector(`#nav button[data-page="${key}"]`);if(b)setTimeout(()=>b.click(),20);
  }

  function classifyAlerts(){
    document.querySelectorAll('#alerts p').forEach(p=>{
      p.classList.remove('at-alert-min','at-alert-critical');
      const m=p.textContent.match(/(\d+)\s*un\.\s*•\s*mínimo\s*(\d+)/i);if(!m)return;
      const stock=Number(m[1]),min=Number(m[2]);p.classList.add(stock<min?'at-alert-critical':'at-alert-min');
    });
  }

  function standaloneShell(){
    if(document.querySelector('.app')||document.querySelector('.at-standalone-sidebar'))return;
    const main=document.querySelector('main');if(!main)return;
    const path=location.pathname.toLowerCase();
    const current=path.includes('transferencias')?'transfer':path.includes('caixa')?'cash':path.includes('movimentacoes')?'movimentos':path.includes('compras')?'compras':path.includes('editar-produtos')?'estoque':'';if(!current)return;
    document.body.classList.add('at-standalone-with-shell');
    const aside=document.createElement('aside');aside.className='at-standalone-sidebar';
    const links=[['dashboard','/','Dashboard'],['pdv','/#pdv','PDV / Venda'],['estoque','/#estoque','Produtos'],['movimentos','/movimentacoes.html','Movimentos'],['compras','/compras.html','Compras / NF-e'],['cash','/caixa.html','Caixa'],['transfer','/transferencias.html','Transferências']];
    aside.innerHTML=`<div class="at-standalone-brand"><span class="mark">AT</span><span>ADEGA <b>TORRES</b></span></div><nav class="at-standalone-nav">${links.map(([k,href,label])=>`<a href="${href}" class="${current===k?'active':''}">${icon(k)}<span>${label}</span></a>`).join('')}</nav><div class="at-standalone-footer"><strong>Adega Torres</strong>Operação integrada • PostgreSQL</div>`;
    document.body.prepend(aside);
    const style=document.createElement('style');style.textContent='@media(max-width:760px){.at-standalone-nav{display:flex!important;overflow-x:auto!important}.at-standalone-nav a{flex:0 0 78px!important}}';document.head.appendChild(style);
  }

  function improveCartBadge(){
    const badge=document.querySelector('.at-cart-badge');if(!badge)return;
    if(!badge.getAttribute('aria-label'))badge.setAttribute('aria-label','Itens diferentes no carrinho');
    if(badge.textContent.trim()==='0'&&!badge.hidden)badge.hidden=true;
  }

  async function tenantContext(){
    const app=document.querySelector('.app'),token=localStorage.getItem('at_token');if(!app||!token)return;
    const api=`http://${location.hostname}:8000`,headers={Authorization:`Bearer ${token}`};
    try{
      const meResponse=await fetch(api+'/auth/me',{headers});if(!meResponse.ok)return;
      const me=await meResponse.json(),ctx=me.context,store=ctx.stores.find(s=>s.id===ctx.selected_store_id);
      const subtitle=document.querySelector('.app main>.top>div>.muted');if(subtitle)subtitle.textContent=`${ctx.company.name} • ${store?.name||'Sem loja'}`;
      const userRole=document.querySelector('.app aside .user .muted');if(userRole)userRole.textContent=ctx.role.name;
      const nav=document.getElementById('nav');
      const addLink=(key,href,label)=>{if(!nav||nav.querySelector(`[data-module-link="${key}"]`))return;const link=document.createElement('a');link.href=href;link.dataset.moduleLink=key;link.className='at-module-link';link.innerHTML=icon(key)+`<span>${label}</span>`;nav.appendChild(link)};
      if(ctx.permissions.includes('cash.read'))addLink('cash','/caixa.html','Caixa');
      if(ctx.permissions.includes('inventory.transfer'))addLink('transfer','/transferencias.html','Transferências');
      if(nav&&(ctx.permissions.includes('users.manage')||ctx.permissions.includes('stores.manage'))&&!nav.querySelector('[data-admin-link]')){
        const link=document.createElement('a');link.href='/admin.html';link.dataset.adminLink='true';link.className='at-module-link at-admin-link';link.innerHTML=icon('admin')+'<span>Administração</span>';nav.appendChild(link);
      }
      const contextsResponse=await fetch(api+'/auth/contexts',{headers});if(!contextsResponse.ok)return;
      const contexts=await contextsResponse.json(),choices=contexts.flatMap(c=>c.stores.map(s=>({companyId:c.company.id,storeId:s.id,label:`${c.company.name} • ${s.name}`})));
      if(choices.length>1){
        const right=document.querySelector('.at-top-right')||document.querySelector('.app main>.top');let select=right.querySelector('.at-context-select');
        if(!select){select=document.createElement('select');select.className='at-context-select';right.prepend(select)}
        select.innerHTML=choices.map(c=>`<option value="${c.companyId}:${c.storeId}" ${c.companyId===ctx.company.id&&c.storeId===ctx.selected_store_id?'selected':''}>${c.label}</option>`).join('');
        select.onchange=async()=>{const[company_id,store_id]=select.value.split(':').map(Number),response=await fetch(api+'/auth/switch-context',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({company_id,store_id})});if(!response.ok)return;const data=await response.json();localStorage.setItem('at_token',data.access_token);localStorage.setItem('at_user',JSON.stringify(data.user));location.reload()};
      }
    }catch{}
  }

  function watchTenantLogin(){
    const app=document.querySelector('.app');if(!app)return;
    new MutationObserver(()=>{if(!app.classList.contains('hidden'))setTimeout(tenantContext,100)}).observe(app,{attributes:true,attributeFilter:['class']});
  }

  function observeDynamic(){
    const app=document.querySelector('.app');if(!app)return;
    let scheduled=false;
    new MutationObserver(()=>{
      if(scheduled)return;scheduled=true;
      requestAnimationFrame(()=>{scheduled=false;cleanStatus();arrangeTop();improveCartBadge();classifyAlerts()});
    }).observe(app,{childList:true,subtree:true,characterData:true});
  }

  function init(){cleanStatus();arrangeTop();fixTitles();handleHash();classifyAlerts();standaloneShell();improveCartBadge();observeDynamic();watchTenantLogin();tenantContext();document.documentElement.classList.add('premium-v2-ready')}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
