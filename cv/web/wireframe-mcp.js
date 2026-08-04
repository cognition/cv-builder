document.addEventListener("DOMContentLoaded",()=>{
  const nav=document.querySelector("#mcp-nav"),view=document.querySelector("#mcp");
  nav.addEventListener("click",()=>{
    document.querySelectorAll(".view").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll("nav button").forEach(x=>x.classList.remove("active"));
    view.classList.add("active");nav.classList.add("active");
    document.querySelector("#crumb").textContent="CONNECT AI";
    document.querySelector("#title").textContent="Use CV Studio with your assistant";
    window.scrollTo({top:0,behavior:"smooth"});
  });
  function toast(message){const t=document.querySelector("#toast");t.textContent=message;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2100)}
  document.querySelectorAll(".copy").forEach(button=>button.addEventListener("click",async()=>{
    try{await navigator.clipboard.writeText(button.dataset.copy);toast("Copied to clipboard")}
    catch(_error){toast("Copy unavailable in this browser")}
  }));
  document.querySelector("#test-mcp").addEventListener("click",event=>{
    const button=event.currentTarget,result=document.querySelector("#test-result");
    button.textContent="Checking…";button.disabled=true;result.textContent="";
    setTimeout(()=>{button.textContent="Test connection";button.disabled=false;result.textContent="✓ Prototype connection successful"},900);
  });
  document.querySelectorAll(".variant-card").forEach(card=>{
    card.querySelectorAll(".level-tabs button").forEach(button=>button.addEventListener("click",()=>{
      card.querySelectorAll(".level-tabs button").forEach(x=>x.classList.remove("active"));button.classList.add("active");
      const copy=card.dataset[button.dataset.level];card.querySelector(".variant-copy").textContent=copy;
      card.querySelector(".length").textContent=copy.trim().split(/\s+/).length+" words";
    }));
    card.querySelector(".compare").addEventListener("click",()=>{
      const overlay=document.createElement("div");overlay.className="compare-popover";
      overlay.innerHTML=`<div class="compare-panel"><header><div><h2>${card.querySelector("h3").textContent}</h2><p>Compare all writing depths side by side.</p></div><button aria-label="Close">×</button></header><div class="compare-grid"><div><b>Brief</b><p>${card.dataset.brief}</p></div><div><b>Standard</b><p>${card.dataset.standard}</p></div><div><b>Detailed</b><p>${card.dataset.detailed}</p></div></div></div>`;
      document.body.appendChild(overlay);overlay.addEventListener("click",event=>{if(event.target===overlay||event.target.closest("header button"))overlay.remove()});
    });
  });
});
