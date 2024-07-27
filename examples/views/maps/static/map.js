class ParksMap {
  constructor(element, center, markerClickedCallback) {
    this.map = L.map(element).setView(center, 6);
    this.markers = [];
    this.markerClickedCallback = markerClickedCallback;

    L.tileLayer("http://{s}.tile.osm.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(this.map);

    this.markerClickedCallback = markerClickedCallback;
  }

  addMarker(park) {
    const marker = L.marker(park.latLng, { parkId: park.name })
      .addTo(this.map)
      .bindPopup(`<b>${park.icon} ${park.name}</b><p>${park.description}</p>`);

    marker.on("click", () => this.markerClickedCallback(park));

    this.markers.push(marker);

    return marker;
  }

  highlightMarker(park) {
    const marker = this.markers.find((m) => m.options.parkId === park.name);
    if (!marker) {
      console.error("Marker not found");
      return;
    }

    marker.openPopup();
    this.map.panTo(marker.getLatLng());
  }
}

window.Hooks = {};

Hooks.ParksMap = {
  mounted() {
    this.map = new ParksMap(this.el, [44.428, -110.5885], (event) => {
      this.pushEvent("highlight-park", event);
    });

    const parks = JSON.parse(this.el.dataset.parks);
    parks.forEach((park) => {
      this.map.addMarker(park);
    });

    this.map.highlightMarker(parks[0], false);

    this.handleEvent("highlight-park", (park) => {
      this.map.highlightMarker(park);
    });
  },
};
