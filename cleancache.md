(async () => {
  try {
    // Cache Storage (PWA / SW)
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    }
    // Service Workers
    if (navigator.serviceWorker) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(r => r.unregister()));
    }
    // local/session storage
    localStorage.clear?.(); 
    sessionStorage.clear?.();
    // IndexedDB
    if (indexedDB?.databases) {
      const dbs = await indexedDB.databases();
      await Promise.all(dbs.map(db => db?.name && indexedDB.deleteDatabase(db.name)));
    }
    console.log('✅ Limpou Cache Storage, SWs, localStorage, sessionStorage e IndexedDB');
  } catch (e) {
    console.warn('⚠️ Algo falhou:', e);
  } finally {
    // Recarrega sem usar o cache *se* "Disable cache" estiver marcado no DevTools
    location.reload();
  }
})();
