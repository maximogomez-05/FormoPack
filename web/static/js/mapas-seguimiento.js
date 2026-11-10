/* Consultas acotadas y antigüedad GPS compartidas por ambos mapas. */
(() => {
  'use strict';
  class ConsultaPeriodica {
    constructor(url, recibir, fallar, intervalo = 10000) {
      Object.assign(this, {url, recibir, fallar, intervalo, activa: false, controlador: null});
      this.reanudar = () => { if (!this.habilitada) return; if (!document.hidden) this.iniciar(); else this.pausar(); };
      document.addEventListener('visibilitychange', this.reanudar);
      window.addEventListener('pageshow', this.reanudar);
      window.addEventListener('pagehide', () => this.pausar());
    }
    iniciar() { this.habilitada = true; this.activa = true; return this.consultar(); }
    pausar() {
      this.activa = false;
      clearTimeout(this.temporizador);
      if (this.controlador) this.controlador.abort();
    }
    async consultar() {
      if (this.controlador || !this.activa || document.hidden) return;
      clearTimeout(this.temporizador);
      const controlador = new AbortController();
      this.controlador = controlador;
      const limite = setTimeout(() => controlador.abort(), 8000);
      try {
        const respuesta = await fetch(this.url, {signal: controlador.signal, cache: 'no-store', credentials: 'same-origin'});
        if (!respuesta.ok) throw new Error('Consulta no disponible');
        const datos = await respuesta.json();
        if (controlador.signal.aborted || !this.activa) return;
        this.recibir(datos);
      } catch (error) {
        if (this.activa && !document.hidden) this.fallar(error);
      } finally {
        clearTimeout(limite);
        this.controlador = null;
        if (this.activa && !document.hidden) this.temporizador = setTimeout(() => this.consultar(), this.intervalo);
      }
    }
  }
  function fechaGps(valor) {
    if (typeof valor !== 'string' || !valor.trim()) return NaN;
    // MariaDB devuelve la hora de Formosa sin offset. No interpretarla en la zona del visitante.
    let texto = valor.trim().replace(' ', 'T');
    if (!/(Z|[+-]\d{2}:\d{2})$/i.test(texto)) texto += '-03:00';
    return Date.parse(texto);
  }
  function coordenadas(lat, lng) {
    const numerico = valor => typeof valor === 'number' || typeof valor === 'string' && valor.trim() !== '';
    return numerico(lat) && numerico(lng)
      && Number.isFinite(Number(lat)) && Math.abs(Number(lat)) <= 90
      && Number.isFinite(Number(lng)) && Math.abs(Number(lng)) <= 180;
  }
  function reciente(fecha) {
    const antiguedad = Date.now() - fechaGps(fecha);
    return Number.isFinite(antiguedad) && antiguedad >= -60000 && antiguedad <= 300000;
  }
  window.FormoPackMapas = {ConsultaPeriodica, fechaGps, coordenadas, reciente};
})();
