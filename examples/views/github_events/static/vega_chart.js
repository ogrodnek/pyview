window.Hooks = window.Hooks ?? {};

window.Hooks.VegaChart = {
  mounted() {
    this._hoverDebounceTimer = null;
    this._lastHoveredTime = null;
    this.renderChart();
  },
  updated() {
    this.renderChart();
  },
  destroyed() {
    if (this._hoverDebounceTimer) {
      clearTimeout(this._hoverDebounceTimer);
    }
  },
  renderChart() {
    const chartSpec = JSON.parse(this.el.dataset.chartSpec);
    if (!chartSpec || !chartSpec.mark) return;
    const chartContainer = this.el;
    const loadingEl = chartContainer.querySelector(".chart-loading");

    vegaEmbed(chartContainer, chartSpec, {
      actions: false,
      container: "fit",
    })
      .then((result) => {
        this.view = result.view;
        if (loadingEl) loadingEl.remove();
        this._attachHoverListener();
      })
      .catch((error) => {
        console.error("Error rendering Vega chart:", error);
        if (loadingEl) loadingEl.remove();
        chartContainer.innerHTML = `<div class="chart-error">Error rendering chart</div>`;
      });
  },
  _toIsoMinute(timeValue) {
    const date = new Date(timeValue);
    if (isNaN(date.getTime())) return null;
    const iso = date.toISOString();
    return iso.replace(/:\d{2}\.\d{3}Z$/, ":00");
  },
  _attachHoverListener() {
    if (!this.view) return;

    this.view.addEventListener("pointerover", (_event, item) => {
      if (!item || !item.datum || item.datum.time == null) return;

      if (this._hoverDebounceTimer) {
        clearTimeout(this._hoverDebounceTimer);
      }

      this._hoverDebounceTimer = setTimeout(() => {
        const timeValue = item.datum.time;
        if (timeValue === this._lastHoveredTime) return;
        this._lastHoveredTime = timeValue;

        const isoMinute = this._toIsoMinute(timeValue);
        if (!isoMinute) return;

        this.pushEvent("chart-hover", {
          time: isoMinute,
          chart: this.el.id,
        });
      }, 150);
    });

    // Clear on mouse leaving chart area
    const vegaEl = this.el.querySelector("canvas, svg");
    if (vegaEl) {
      vegaEl.addEventListener("pointerleave", () => {
        if (this._hoverDebounceTimer) {
          clearTimeout(this._hoverDebounceTimer);
        }
        if (this._lastHoveredTime !== null) {
          this._lastHoveredTime = null;
          this.pushEvent("chart-hover-clear", { chart: this.el.id });
        }
      });
    }
  },
};
