import pandas as pd
import folium
from geopy.distance import geodesic
import numpy as np
import re
# import networkx as nx # Se for usar para Dijkstra na malha ou centralidade

# --- Configuration ---
STOPS_FILE = "script/data/moovit_stops_geocoded_filtered.csv"
MAIN_STREET_NAMES = [
    "Carlos Mariguella",
    "Carlos Marighella",
    "Vitória Régia",  # Old name, now Carlos Mariguella
]
MAX_ACCEPTABLE_DISTANCE_METERS = 450  # For suggesting new stops
MAP_CENTER_LAT, MAP_CENTER_LON = -22.9367, -42.9751

# --- Helper Functions ---
def load_stops_data(filepath):
    """
    Load and clean Moovit stops data.
    Returns a DataFrame with columns: 'stop_id', 'lat', 'lon', 'address', 'line_name', 'direction', 'stop_order', 'line_number'.
    """
    try:
        df = pd.read_csv(filepath)
        df.rename(columns={
            'latitude': 'lat',
            'longitude': 'lon',
            'endereco_geocodificado': 'address',
            'id_parada': 'stop_id',
            'nome_linha': 'line_name',
            'sentido': 'direction',
            'ordem_parada': 'stop_order',
            'numero_linha': 'line_number',
        }, inplace=True)
        if 'stop_id' not in df.columns:
            df['stop_id'] = df.index
        for col in ['lat', 'lon']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['stop_order'] = pd.to_numeric(df['stop_order'], errors='coerce', downcast='integer')
        required_cols = ['lat', 'lon', 'stop_order', 'address', 'line_name', 'direction', 'line_number']
        df.dropna(subset=required_cols, inplace=True)
        return df
    except FileNotFoundError:
        print(f"Error: Stops file not found at {filepath}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error loading stops data: {e}")
        return pd.DataFrame()

def filter_stops_by_street(df_stops, street_names):
    """
    Filter DataFrame to return only stops on the main street(s), using a case-insensitive substring match.
    """
    if df_stops is None or df_stops.empty or not street_names:
        print("Stops DataFrame is empty or street names list is empty.")
        return pd.DataFrame()
    df_stops['address'] = df_stops['address'].astype(str)
    mask = df_stops['address'].apply(
        lambda addr: any(name.lower() in addr.lower() for name in street_names)
    )
    df_main_street = df_stops[mask].drop_duplicates(subset=['lat', 'lon'])
    print("Filtered stops for main street(s):")
    print(df_main_street[['address', 'line_name', 'direction', 'stop_order']])
    if df_main_street.empty:
        print(f"No stops found containing any of: {street_names} in the address.")
        return pd.DataFrame()
    return df_main_street.reset_index(drop=True)

def classify_distance(distance_m):
    """
    Classify the distance and return the category and corresponding color.
    """
    if pd.isna(distance_m):
        return "No data", "gray"
    if distance_m <= 400:
        return "Near (0-400m)", "green"
    elif distance_m <= 600:
        return "Reasonable (400-600m)", "gold"
    elif distance_m <= 800:
        return "Medium (600-800m)", "orange"
    elif distance_m <= 1200:
        return "Far (800-1200m)", "red"
    else:
        return "Very Far (>1200m)", "purple"

def create_main_street_map(df_stops_main_street):
    """
    Create and save the map for the main street analysis.
    - Groups stops by coordinates.
    - Orders stops by stop_order and proximity.
    - Draws sequential edges colored by distance.
    - Shows only the address on hover, all info in popup.
    - Suggests new stops where gaps are too large.
    """
    if df_stops_main_street is None or df_stops_main_street.empty:
        print("No stop data to generate the map.")
        return None
    m = folium.Map(location=[MAP_CENTER_LAT, MAP_CENTER_LON], zoom_start=14)
    grouped = df_stops_main_street.groupby(['lat', 'lon'])
    points = list(grouped.groups.keys())
    # Order by stop_order (if available), then by proximity
    points_ordered = []
    if 'stop_order' in df_stops_main_street.columns and not df_stops_main_street['stop_order'].isnull().all():
        order_by_point = grouped['stop_order'].min().to_dict()
        points_ordered = sorted(points, key=lambda x: (order_by_point.get(x, float('inf')), x[0], x[1]))
    else:
        points_ordered = points
    # Build a sequential path by nearest neighbor
    visited = set()
    path = []
    if points_ordered:
        current = points_ordered[0]
        path.append(current)
        visited.add(current)
        while len(visited) < len(points_ordered):
            min_dist = float('inf')
            next_point = None
            for p in points_ordered:
                if p in visited:
                    continue
                dist = (p[0] - current[0])**2 + (p[1] - current[1])**2
                if dist < min_dist:
                    min_dist = dist
                    next_point = p
            if next_point is not None:
                path.append(next_point)
                visited.add(next_point)
                current = next_point
            else:
                break
    else:
        path = points_ordered
    # Calculate gaps (distances) only for the drawn edges
    gaps = []
    for i in range(len(path) - 1):
        p1 = path[i]
        p2 = path[i+1]
        dist = geodesic(p1, p2).meters
        if dist > MAX_ACCEPTABLE_DISTANCE_METERS:
            gaps.append({
                'lat': (p1[0] + p2[0]) / 2,
                'lon': (p1[1] + p2[1]) / 2,
                'reason': f"Gap of {dist:.0f}m between sequential stops"
            })
    # Add stop markers
    for (lat, lon), group in grouped:
        addresses = group['address'].unique()
        stop_ids = group['stop_id'].unique()
        lines = group[['line_number', 'line_name']].drop_duplicates().values.tolist()
        directions = group['direction'].unique()
        orders = group['stop_order'].unique()
        lines_str = '<br>'.join([f"<b>{num if pd.notna(num) else ''}</b> - {name if pd.notna(name) else ''}" for num, name in lines])
        addresses_str = '<br>'.join(addresses)
        directions_str = ', '.join(directions)
        stop_ids_str = ', '.join([str(x) for x in stop_ids])
        orders_str = ', '.join([str(x) for x in orders])
        # Tooltip: only main address
        tooltip_text = addresses[0] if len(addresses) > 0 else "No address"
        # Popup: todas as informações em português
        popup_text = f"<b>Endereço(s):</b> {addresses_str}<br>"
        popup_text += f"<b>Latitude:</b> {lat}<br>"
        popup_text += f"<b>Longitude:</b> {lon}<br>"
        popup_text += f"<b>Sentido(s):</b> {directions_str}<br>"
        popup_text += f"<b>Ordem da parada(s):</b> {orders_str}<br>"
        popup_text += f"<b>ID(s) da parada:</b> {stop_ids_str}<br>"
        popup_text += f"<b>Linhas:</b><br>{lines_str}"
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color='blue',
            fill=True,
            fill_color='blue',
            fill_opacity=0.7,
            tooltip=folium.Tooltip(tooltip_text),
            popup=folium.Popup(popup_text, max_width=400)
        ).add_to(m)
    # Draw sequential edges (linear graph, ordered)
    for i in range(len(path) - 1):
        p1_lat, p1_lon = path[i]
        p2_lat, p2_lon = path[i+1]
        dist = geodesic((p1_lat, p1_lon), (p2_lat, p2_lon)).meters
        class_dist, color = classify_distance(dist)
        folium.PolyLine(
            [(p1_lat, p1_lon), (p2_lat, p2_lon)],
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=f"Distance: {dist:.0f}m ({class_dist})"
        ).add_to(m)
    # Add only gaps based on the new edges
    for gap in gaps:
        if pd.notna(gap['lat']) and pd.notna(gap['lon']):
            folium.Marker(
                location=[gap['lat'], gap['lon']],
                tooltip=gap['reason'],
                icon=folium.Icon(color='black', icon='plus-sign', prefix='glyphicon')
            ).add_to(m)
    map_filename = 'script/tests/principal-carlos-marighella/map.html'
    m.save(map_filename)
    print(f"Map '{map_filename}' generated.")
    return m

# --- Main Flow ---
if __name__ == "__main__":
    df_all_stops = load_stops_data(STOPS_FILE)
    if df_all_stops is not None and not df_all_stops.empty:
        df_main_street_stops = filter_stops_by_street(df_all_stops.copy(), MAIN_STREET_NAMES)
        if df_main_street_stops is not None and not df_main_street_stops.empty:
            create_main_street_map(df_main_street_stops)
        else:
            print(f"No stops found or processed for streets: {MAIN_STREET_NAMES}")
    else:
        print("Could not load stops data. Exiting script.")
