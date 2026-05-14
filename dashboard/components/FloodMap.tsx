"use client";

import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";

export default function FloodMap() {
  return (
    <MapContainer
      center={[12.9716, 77.5946]}
      zoom={11}
      style={{ height: "100vh", width: "100%" }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <Marker position={[12.9716, 77.5946]}>
        <Popup>
          Flood Risk Area
        </Popup>
      </Marker>
    </MapContainer>
  );
}
