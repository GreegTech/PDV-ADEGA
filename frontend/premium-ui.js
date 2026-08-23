(()=>{
  const path=(location.pathname.split('/').pop()||'index.html').replace('.html','').replace(/[^a-z0-9-]/gi,'-').toLowerCase();
  document.body.classList.add('page-'+path);

  function toast(message,type='ok',timeout=2600){
    let stack=document.querySelector('.at-toast-stack');
    if(!stack){stack=document.createElement('div');stack.className='at-toast-stack';document.body.appendChild(stack)}
    const el=document.createElement('div');el.className='at-toast '+type;el.textContent=message;stack.appendChild(el);
    setTimeout(()=>{el.style.opacity='0';el.style.transform='translateY(6px)';setTimeout(()=>el.remove(),180)},timeout);
  }
  window.atToast=toast;

  function addClock(){
    const top=document.querySelector('.app main>.top');
    if(!top||document.querySelector('.at-clock'))return;
    const clock=document.createElement('div');clock.className='at-clock';
    const status=document.getElementById('status');
    if(status)top.insertBefore(clock,status);else top.appendChild(clock);
    const tick=()=>{const d=new Date();clock.innerHTML=`<span>Hoje</span><strong>${d.toLocaleDateString('pt-BR',{day:'2-digit',month:'short'})} • ${d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}</strong>`};
    tick();setInterval(tick,30000);
  }

  function addSearchShortcut(){
    const search=document.getElementById('searchProduct');
    if(!search)return;
    search.setAttribute('autocomplete','off');search.setAttribute('aria-label','Buscar ou bipar produto');
    document.addEventListener('keydown',e=>{
      if(e.key==='F2'||((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k')){
        e.preventDefault();search.focus();search.select();
      }
      if(e.key==='Escape'&&document.activeElement===search){search.value='';search.dispatchEvent(new Event('input',{bubbles:true}));search.blur()}
    });
  }

  function enhancePayments(){
    const labels={PIX:'Receber por PIX',Dinheiro:'Receber em dinheiro','Débito':'Receber no débito','Crédito':'Receber no crédito'};
    document.querySelectorAll('.payBtn').forEach(b=>{b.title=labels[b.dataset.method]||b.textContent.trim();b.setAttribute('aria-label',b.title)});
  }

  function cartBadge(){
    const nav=document.querySelector('[data-page="pdv"]'),cart=document.getElementById('cart');
    if(!nav||!cart)return;
    let badge=nav.querySelector('.at-cart-badge');
    if(!badge){badge=document.createElement('span');badge.className='at-cart-badge';badge.hidden=true;nav.appendChild(badge)}
    const update=()=>{const count=cart.querySelectorAll('.cart-item').length;badge.textContent=count;badge.hidden=count===0};
    new MutationObserver(update).observe(cart,{childList:true,subtree:true});update();
  }

  function annotateStandalone(){
    if(document.querySelector('.app'))return;
    const main=document.querySelector('main');if(!main)return;
    main.setAttribute('data-premium-shell','true');
    document.querySelectorAll('a.btn').forEach(a=>{a.setAttribute('role','button')});
  }

  function monitorNotices(){
    const sale=document.getElementById('saleNotice');if(!sale)return;
    let previous='';
    new MutationObserver(()=>{const text=sale.textContent.trim();if(text&&text!==previous&&/Venda #\d+ concluída/i.test(text)){toast('Venda concluída com sucesso','ok',2200)}previous=text}).observe(sale,{childList:true,subtree:true});
  }

  function init(){
    addClock();addSearchShortcut();enhancePayments();cartBadge();annotateStandalone();monitorNotices();
    document.documentElement.classList.add('premium-ready');
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
