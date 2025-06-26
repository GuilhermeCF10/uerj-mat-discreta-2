import pandas as pd
import folium
from geopy.distance import geodesic
import numpy as np
import networkx as nx

# --- Configuration ---
STOPS_FILE = "script/data/moovit_stops_geocoded_filtered.csv"
MAP_CENTER_LAT, MAP_CENTER_LON = -22.9367, -42.9751

# Defina as coordenadas de origem e destino desejadas aqui (latitude, longitude).
# Se deixadas como None, o script usará a primeira e última parada do arquivo CSV.
# Exemplo de coordenadas (extraídas do readme para demonstração):
# USER_SOURCE_COORD = (-22.9033137, -42.9369153)
# USER_TARGET_COORD = (-22.9008428, -42.93906579999999)
USER_SOURCE_COORD = (-22.9672379, -42.9099213)
USER_TARGET_COORD = (-22.9675662, -42.9707889)


# --- Helper Functions ---
def load_stops_data(filepath):
    """
    Carrega e limpa os dados das paradas do Moovit.
    Retorna um DataFrame com as colunas originais do CSV.
    """
    try:
        df = pd.read_csv(filepath)
        # Não faz mais rename, usa os nomes originais do CSV
        if 'id_parada' not in df.columns:
            df['id_parada'] = df.index
        for col in ['latitude', 'longitude']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['ordem_parada'] = pd.to_numeric(df['ordem_parada'], errors='coerce', downcast='integer')
        required_cols = ['latitude', 'longitude', 'ordem_parada', 'endereco_geocodificado', 'nome_linha', 'sentido', 'numero_linha']
        df.dropna(subset=required_cols, inplace=True)
        return df
    except FileNotFoundError:
        print(f"Erro: Arquivo de paradas não encontrado em {filepath}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Erro ao carregar dados das paradas: {e}")
        return pd.DataFrame()

def build_graph_from_stops(df_stops):
    """
    Constrói um grafo multimodal: cada nó é uma coordenada (lat, lon), agregando todas as linhas, ids, sentidos, ordens, endereços.
    Arestas conectam nós consecutivos na ordem de cada linha/sentido.
    """
    G = nx.DiGraph()
    # Agregar informações por coordenada
    grouped_coords = df_stops.groupby(['latitude', 'longitude'])
    node_data = {}
    for (lat, lon), group in grouped_coords:
        node_data[(lat, lon)] = {
            'ids': list(group['id_parada'].unique()),
            'enderecos': list(group['endereco_geocodificado'].unique()),
            'linhas': list(group['nome_linha'].unique()),
            'numeros_linha': list(group['numero_linha'].unique()),
            'sentidos': list(group['sentido'].unique()),
            'ordens': list(group['ordem_parada'].unique()),
        }
    # Adicionar nós
    for (lat, lon), data in node_data.items():
        G.add_node((lat, lon), **data, lat=lat, lon=lon)
    # Adicionar arestas por linha/sentido
    for _, group in df_stops.groupby(['numero_linha', 'sentido']):
        group_sorted = group.sort_values('ordem_parada')
        prev_coord = None
        for _, row in group_sorted.iterrows():
            coord = (row['latitude'], row['longitude'])
            if prev_coord is not None and prev_coord != coord:
                dist = geodesic(prev_coord, coord).meters
                G.add_edge(prev_coord, coord, weight=dist, numero_linha=row['numero_linha'], nome_linha=row['nome_linha'])
            prev_coord = coord
    return G

def dijkstra_shortest_path(G, source, target):
    """
    Find shortest path using Dijkstra's algorithm.
    Returns the path and total cost.
    """
    try:
        path = nx.dijkstra_path(G, source, target, weight='weight')
        cost = nx.dijkstra_path_length(G, source, target, weight='weight')
        return path, cost
    except nx.NetworkXNoPath:
        return None, float('inf')

def astar_shortest_path(G, source, target):
    """
    Find shortest path using A* algorithm.
    Returns the path and total cost.
    """
    def heuristic(u, v):
        lat_u, lon_u = G.nodes[u]['lat'], G.nodes[u]['lon']
        lat_v, lon_v = G.nodes[v]['lat'], G.nodes[v]['lon']
        return geodesic((lat_u, lon_u), (lat_v, lon_v)).meters
    try:
        path = nx.astar_path(G, source, target, heuristic=heuristic, weight='weight')
        cost = nx.astar_path_length(G, source, target, heuristic=heuristic, weight='weight')
        return path, cost
    except nx.NetworkXNoPath:
        return None, float('inf')

def node_centrality_analysis(G):
    """
    Count how many times each node appears in all lines (centrality by repetition).
    Returns a dict: node_id -> count.
    """
    centrality = {}
    for node in G.nodes:
        centrality[node] = len(G.in_edges(node)) + len(G.out_edges(node))
    return centrality

def classify_distance(distance_m):
    if pd.isna(distance_m):
        return "Sem dados", "gray"
    if distance_m <= 400:
        return "Perto (0-400m)", "green"
    elif distance_m <= 600:
        return "Razoável (400-600m)", "gold"
    elif distance_m <= 800:
        return "Médio (600-800m)", "orange"
    elif distance_m <= 1200:
        return "Longe (800-1200m)", "red"
    else:
        return "Muito longe (>1200m)", "purple"

def create_graph_map(G, centrality=None, highlight_path=None):
    """
    Visualize the real bus stop graph.
    - Nodes: bus stops (size/color by centrality if provided)
    - Edges: real connections (color by distance)
    - Optionally highlight a path (Dijkstra/A*)
    - Destaca os top 5 nós mais centrais em amarelo/verde
    """
    m = folium.Map(location=[MAP_CENTER_LAT, MAP_CENTER_LON], zoom_start=14)
    # Draw edges (todas as arestas em cinza)
    for u, v, data in G.edges(data=True):
        lat_u, lon_u = u
        lat_v, lon_v = v
        dist = data['weight']
        folium.PolyLine(
            [(lat_u, lon_u), (lat_v, lon_v)],
            color='#888',  # cinza neutro
            weight=3,
            opacity=0.6,
            tooltip=f"Distância: {dist:.0f}m"
        ).add_to(m)
    # Identificar top 5 centrais
    top_central_nodes = set()
    if centrality:
        top_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]
        top_central_nodes = set([node for node, _ in top_central])
    # Draw nodes
    for node, data in G.nodes(data=True):
        if centrality and node in top_central_nodes:
            c = 'yellow'
            fill_c = 'lime'
            radius = 12
            tooltip_extra = f"Parada central (grau {centrality[node]})"
        else:
            c = 'blue'
            fill_c = 'blue'
            radius = 5
            tooltip_extra = None
        enderecos_str = '<br>'.join(data['enderecos']) if 'enderecos' in data else '-'
        ids_str = ', '.join(str(x) for x in data['ids']) if 'ids' in data else '-'
        linhas_str = '<br>'.join(str(x) for x in data['linhas']) if 'linhas' in data else '-'
        numeros_linha_str = ', '.join(str(x) for x in data['numeros_linha']) if 'numeros_linha' in data else '-'
        sentidos_str = ', '.join(str(x) for x in data['sentidos']) if 'sentidos' in data else '-'
        ordens_str = ', '.join(str(x) for x in data['ordens']) if 'ordens' in data else '-'
        folium.CircleMarker(
            location=[data['lat'], data['lon']],
            radius=radius,
            color=c,
            fill=True,
            fill_color=fill_c,
            fill_opacity=0.85 if (centrality and node in top_central_nodes) else 0.7,
            tooltip=(f"{enderecos_str}<br>{tooltip_extra}" if tooltip_extra else enderecos_str),
            popup=folium.Popup(
                f"<b>Endereço(s):</b> {enderecos_str}<br>"
                f"<b>Latitude:</b> {data['lat']}<br>"
                f"<b>Longitude:</b> {data['lon']}<br>"
                f"<b>Sentido(s):</b> {sentidos_str}<br>"
                f"<b>Ordem da parada(s):</b> {ordens_str}<br>"
                f"<b>ID(s) da parada:</b> {ids_str}<br>"
                f"<b>Linhas:</b><br>{numeros_linha_str} - {linhas_str}" +
                (f"<br><b>Parada central (grau {centrality[node]})</b>" if (centrality and node in top_central_nodes) else ""),
                max_width=400
            )
        ).add_to(m)
    # Highlight path if provided
    if highlight_path:
        path_coords = [(n[0], n[1]) for n in highlight_path]
        folium.PolyLine(
            path_coords,
            color='black',
            weight=7,
            opacity=0.9,
            tooltip="Caminho ótimo"
        ).add_to(m)
    map_filename = 'script/tests/otimizacao/map.html'
    m.save(map_filename)
    print(f"Mapa '{map_filename}' gerado.")
    return m

# --- Main Flow ---
if __name__ == "__main__":
    df_all_stops = load_stops_data(STOPS_FILE)
    if df_all_stops is not None and not df_all_stops.empty:
        G = build_graph_from_stops(df_all_stops)
        centrality = node_centrality_analysis(G)

        # --- Escolha de dois pontos para simulação ---
        source = None
        target = None

        if USER_SOURCE_COORD and USER_TARGET_COORD:
            source = USER_SOURCE_COORD
            target = USER_TARGET_COORD
            print(f"Usando coordenadas definidas pelo usuário: Origem={source}, Destino={target}")
            if source not in G:
                print(f"Erro: Nó de origem {source} não encontrado no grafo. Verifique as coordenadas.")
                print("Abortando.")
                exit()
            if target not in G:
                print(f"Erro: Nó de destino {target} não encontrado no grafo. Verifique as coordenadas.")
                print("Abortando.")
                exit()
        else:
            print("Coordenadas de usuário não definidas. Usando a primeira e última parada do CSV como padrão.")
            if not df_all_stops.empty:
                source = (df_all_stops.iloc[0]['latitude'], df_all_stops.iloc[0]['longitude'])
                target = (df_all_stops.iloc[-1]['latitude'], df_all_stops.iloc[-1]['longitude'])
                print(f"Origem padrão: {source}, Destino padrão: {target}")
            else:
                print("Erro: DataFrame de paradas está vazio. Não é possível definir origem/destino padrão.")
                print("Abortando.")
                exit()
        
        if source is None or target is None:
            print("Erro: Pontos de origem e/ou destino não puderam ser definidos.")
            print("Abortando.")
            exit()

        # --- Dijkstra ---
        path_dij, cost_dij = dijkstra_shortest_path(G, source, target)
        if path_dij is not None and isinstance(path_dij, list):
            print(f"Caminho ótimo (Dijkstra) de {source} para {target}:")
            for n in path_dij:
                print(f"  - {n} | {G.nodes[n]['enderecos']}")
            print(f"Distância total: {cost_dij:.0f}m")
            print(f"Número de paradas no caminho: {len(path_dij)}")
        else:
            print("Não existe caminho entre as paradas selecionadas (Dijkstra).")

        # --- A* ---
        path_astar, cost_astar = astar_shortest_path(G, source, target)
        if path_astar is not None and isinstance(path_astar, list):
            print(f"Caminho ótimo (A*) de {source} para {target}:")
            for n in path_astar:
                print(f"  - {n} | {G.nodes[n]['enderecos']}")
            print(f"Distância total: {cost_astar:.0f}m")
            print(f"Número de paradas no caminho: {len(path_astar)}")
        else:
            print("Não existe caminho entre as paradas selecionadas (A*).")

        # --- Centralidade ---
        top_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]
        print("Paradas mais centrais (maior grau de passagem):")
        for node, grau in top_central:
            print(f"  - {node} | {G.nodes[node]['enderecos']} | grau: {grau}")

        # --- Mapa com destaque do caminho ótimo (Dijkstra) ---
        create_graph_map(G, centrality, highlight_path=path_dij)
    else:
        print("Não foi possível carregar os dados das paradas.")
