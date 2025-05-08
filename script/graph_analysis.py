import networkx as nx
import pandas as pd
from geopy.distance import geodesic # Para calcular distância geodésica
import matplotlib.pyplot as plt
import contextily as cx # Para adicionar mapas base
import folium # Para mapas interativos
import webbrowser # Para abrir o mapa no navegador
import os # Para obter o caminho absoluto do arquivo
# import xyzservices.providers as xyz_providers # Removido, usar cx.providers diretamente

def calculate_distance_km(coord1: tuple[float, float] | None, coord2: tuple[float, float] | None) -> float:
    """
    Calcula a distância geodésica em km entre duas coordenadas (lat, lon).
    Retorna float('inf') se alguma coordenada for inválida ou ausente.
    """
    if coord1 is None or coord2 is None or \
       pd.isna(coord1[0]) or pd.isna(coord1[1]) or \
       pd.isna(coord2[0]) or pd.isna(coord2[1]):
        return float('inf')
    try:
        dist = geodesic(coord1, coord2).km
        return dist
    except ValueError: # Pode ocorrer se as coordenadas forem inválidas para geopy
        return float('inf')

def create_transport_graph(df_itinerarios: pd.DataFrame) -> nx.DiGraph:
    """
    Cria um grafo NetworkX direcionado (DiGraph) a partir do DataFrame de itinerários de ônibus.

    Nós: Paradas de ônibus únicas (identificadas por 'parada_nome').
         Atributos dos nós: 'pos' (latitude, longitude), 'nome_completo' (descrição geocodificada).
    Arestas: Conexões diretas entre paradas sequenciais em uma mesma linha e sentido.
             Atributos das arestas: 'weight' (distância em km), 'linha' (código da linha), 'sentido'.
    """
    G = nx.DiGraph()

    paradas_unicas = df_itinerarios.dropna(subset=['parada_nome', 'latitude', 'longitude'])
    paradas_unicas = paradas_unicas.drop_duplicates(subset=['parada_nome'])

    for _, row in paradas_unicas.iterrows():
        nome_parada = row['parada_nome']
        try:
            lat = float(row['latitude'])
            lon = float(row['longitude'])
            if pd.notna(lat) and pd.notna(lon):
                 G.add_node(nome_parada, 
                            pos=(lon, lat),  # IMPORTANTE: NetworkX espera (x, y), contextily espera (lon, lat)
                            latitude=lat, longitude=lon, # Guardar separadamente para clareza
                            nome_completo=row.get('endereco_geocodificado', nome_parada))
        except (ValueError, TypeError):
            # print(f"Aviso: Coordenadas inválidas para a parada '{nome_parada}'. Não será adicionada ao grafo.")
            continue

    df_sorted = df_itinerarios.sort_values(by=['numero_linha', 'sentido', 'ordem_parada'])

    for (numero_linha, sentido), group in df_sorted.groupby(['numero_linha', 'sentido']):
        paradas_sequenciais_nomes = group['parada_nome'].tolist()
        
        for i in range(len(paradas_sequenciais_nomes) - 1):
            parada_origem_nome = paradas_sequenciais_nomes[i]
            parada_destino_nome = paradas_sequenciais_nomes[i+1]

            if G.has_node(parada_origem_nome) and G.has_node(parada_destino_nome):
                # Usar longitude e latitude diretamente para calculate_distance_km
                coord_origem_latlon = (G.nodes[parada_origem_nome]['latitude'], G.nodes[parada_origem_nome]['longitude'])
                coord_destino_latlon = (G.nodes[parada_destino_nome]['latitude'], G.nodes[parada_destino_nome]['longitude'])
                
                distancia = calculate_distance_km(coord_origem_latlon, coord_destino_latlon)

                if distancia != float('inf'):
                    if G.has_edge(parada_origem_nome, parada_destino_nome):
                        if distancia < G[parada_origem_nome][parada_destino_nome]['weight']:
                            G[parada_origem_nome][parada_destino_nome]['weight'] = distancia
                            current_linhas = G[parada_origem_nome][parada_destino_nome].get('linhas_passantes', [])
                            if numero_linha not in current_linhas:
                                G[parada_origem_nome][parada_destino_nome]['linhas_passantes'].append(numero_linha)
                    else:
                        G.add_edge(parada_origem_nome, parada_destino_nome, 
                                   weight=distancia, 
                                   linha=numero_linha, 
                                   linhas_passantes=[numero_linha],
                                   sentido=sentido)
    return G

def find_shortest_path_dijkstra(graph: nx.DiGraph, source_node: str, target_node: str, weight: str = 'weight'):
    """
    Encontra o caminho mais curto usando Dijkstra em um grafo direcionado.
    Retorna (comprimento, lista de nós do caminho) ou (None, mensagem de erro).
    """
    if not graph.has_node(source_node):
        return None, f"Nó de origem '{source_node}' não encontrado no grafo."
    if not graph.has_node(target_node):
        return None, f"Nó de destino '{target_node}' não encontrado no grafo."
        
    try:
        length, path_nodes = nx.single_source_dijkstra(graph, source_node, target_node, weight=weight)
        return length, path_nodes
    except nx.NetworkXNoPath:
        return None, f"Não há caminho entre '{source_node}' e '{target_node}' no grafo."
    except Exception as e:
        return None, f"Erro ao calcular o caminho: {e}"

def get_path_details(graph: nx.DiGraph, path_nodes: list) -> list[dict]:
    """
    Obtém detalhes de cada trecho (aresta) em um caminho.
    Retorna uma lista de dicionários com informações de cada trecho.
    """
    details = []
    if not path_nodes or len(path_nodes) < 2:
        return details
        
    for i in range(len(path_nodes) - 1):
        u = path_nodes[i]
        v = path_nodes[i+1]
        if graph.has_edge(u,v):
            edge_data = graph.get_edge_data(u,v)
            details.append({
                "de": u,
                "para": v,
                "distancia_km": edge_data.get('weight', float('inf')),
                "linha_principal": edge_data.get('linha', 'N/A'), 
                "linhas_passantes": edge_data.get('linhas_passantes', []) 
            })
        else: 
            details.append({
                "de": u,
                "para": v,
                "distancia_km": float('inf'),
                "observacao": "Aresta não encontrada no grafo (inconsistência?)"
            })
    return details 

def plot_transport_graph(graph: nx.DiGraph, 
                         path_to_highlight: list | None = None, 
                         save_path: str | None = None,
                         map_provider_name: str = "OpenStreetMap.Mapnik", 
                         zoom_level: int | str = 12): 
    """
    Desenha o grafo de transporte usando Matplotlib, com um mapa base do contextily.

    Args:
        graph: O grafo NetworkX (DiGraph) a ser desenhado.
        path_to_highlight: Uma lista opcional de nós representando um caminho a ser destacado.
        save_path: Caminho opcional para salvar a imagem (ex: "grafo_transporte.png").
        map_provider_name: String do provedor de mapa (ex: "OpenStreetMap.Mapnik", "CartoDB.Positron").
        zoom_level: Nível de zoom para o mapa base (inteiro recomendado, ex: 12, ou 'auto').
    """
    if not graph.nodes():
        print("Grafo está vazio. Nada para plotar.")
        return

    node_positions = {node: data['pos'] for node, data in graph.nodes(data=True) if 'pos' in data and isinstance(data['pos'], tuple) and len(data['pos']) == 2}
    
    if not node_positions:
        print("Nenhum nó no grafo possui atributo 'pos' (lon, lat) válido. Impossível plotar.")
        return

    fig, ax = plt.subplots(figsize=(18, 15))

    # Nós gerais
    nx.draw_networkx_nodes(graph, node_positions, ax=ax, node_size=35, node_color='deepskyblue', alpha=0.75, linewidths=0.6, edgecolors='darkblue')
    # Arestas gerais
    nx.draw_networkx_edges(graph, node_positions, ax=ax, arrowstyle='-', alpha=0.4, edge_color='darkgray', width=1.0)
    
    # Destacar caminho
    if path_to_highlight and len(path_to_highlight) >= 2:
        path_edges = list(zip(path_to_highlight[:-1], path_to_highlight[1:]))
        valid_path_nodes = [node for node in path_to_highlight if node in node_positions]
        # Nós do caminho
        nx.draw_networkx_nodes(graph, node_positions, ax=ax, nodelist=valid_path_nodes, node_size=60, node_color='orangered', alpha=0.9, linewidths=1, edgecolors='darkred')
        # Arestas do caminho
        nx.draw_networkx_edges(graph, node_positions, ax=ax, edgelist=path_edges, edge_color='red', width=2.8, arrowstyle='->', alpha=0.9)
        # Rótulos do caminho
        path_labels = {node: node for node in valid_path_nodes}
        nx.draw_networkx_labels(graph, node_positions, ax=ax, labels=path_labels, font_size=int(7.5), font_color='black', 
                                bbox=dict(facecolor='white', alpha=0.55, edgecolor='none', pad=0.1))
    else:
        # Rótulos gerais (poucos)
        num_labels_to_show = min(3, graph.number_of_nodes()) 
        if num_labels_to_show > 0:
            labels_to_draw = {node: node for i, node in enumerate(node_positions.keys()) if i < num_labels_to_show}
            nx.draw_networkx_labels(graph, node_positions, ax=ax, labels=labels_to_draw, font_size=int(6.5), font_color='black',
                                    bbox=dict(facecolor='white', alpha=0.45, edgecolor='none', pad=0.1))
    
    map_provider_obj = None
    effective_zoom = zoom_level
    try:
        provider_parts = map_provider_name.split('.')
        temp_obj = cx.providers
        for part in provider_parts:
            if hasattr(temp_obj, part):
                temp_obj = getattr(temp_obj, part)
            else:
                raise AttributeError(f"Parte '{part}' do provedor '{map_provider_name}' não encontrada em cx.providers.")
        map_provider_obj = temp_obj

        longitudes = [pos[0] for pos in node_positions.values()]
        latitudes = [pos[1] for pos in node_positions.values()]
        if longitudes and latitudes:
            margin_lon = (max(longitudes) - min(longitudes)) * 0.05 
            margin_lat = (max(latitudes) - min(latitudes)) * 0.05  
            min_margin = 0.005 
            ax.set_xlim(min(longitudes) - max(margin_lon, min_margin), max(longitudes) + max(margin_lon, min_margin))
            ax.set_ylim(min(latitudes) - max(margin_lat, min_margin), max(latitudes) + max(margin_lat, min_margin))

        if not isinstance(effective_zoom, (int, str)):
             print(f"Nível de zoom '{effective_zoom}' inválido, usando o padrão 12.")
             effective_zoom = 12 
        elif isinstance(effective_zoom, str) and effective_zoom.lower() != 'auto':
            try:
                effective_zoom = int(effective_zoom)
            except ValueError:
                print(f"Nível de zoom '{effective_zoom}' como string não é 'auto' nem um número, usando o padrão 12.")
                effective_zoom = 12 
        elif isinstance(effective_zoom, str) and effective_zoom.lower() == 'auto':
            pass 

        print(f"Tentando usar provedor: {map_provider_name}, zoom: {effective_zoom}")
        cx.add_basemap(ax, crs='EPSG:4326', source=map_provider_obj, zoom=effective_zoom) # type: ignore
        print(f"Mapa base adicionado com {map_provider_name}.")

    except AttributeError as e_attr:
        print(f"Erro ao acessar provedor de mapa '{map_provider_name}': {e_attr}")
        print("Verifique o nome (ex: 'OpenStreetMap.Mapnik') e a instalação/versão das bibliotecas. Plotando sem mapa base.")
    except Exception as e_gen:
        print(f"Erro geral ao adicionar mapa base: {e_gen}. Plotando sem mapa base.")

    final_title_provider = map_provider_name if map_provider_obj else "Nenhum"
    ax.set_title(f"Rede de Transporte (Maricá) - Mapa: {final_title_provider}", fontsize=16)
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    
    if save_path:
        try:
            plt.savefig(save_path, dpi=300, bbox_inches='tight') 
            print(f"Grafo salvo em '{save_path}'")
        except Exception as e:
            print(f"Erro ao salvar o grafo: {e}")
    
    plt.tight_layout() # Descomentado para tentar melhorar o espaçamento
    plt.show() 

def create_interactive_map(graph: nx.DiGraph, 
                           df_itinerarios: pd.DataFrame, 
                           path_to_highlight: list | None = None, 
                           map_filename: str = "interactive_map.html",
                           tile_provider: str = "OpenStreetMap"):
    """
    Cria um mapa HTML interativo usando Folium para visualizar o grafo de transporte.

    Args:
        graph: O grafo NetworkX (DiGraph) a ser desenhado.
        df_itinerarios: DataFrame original para consulta de detalhes das linhas/paradas.
        path_to_highlight: Uma lista opcional de nós (nomes das paradas) representando um caminho a ser destacado.
        map_filename: Nome do arquivo HTML para salvar o mapa interativo.
        tile_provider: Nome do provedor de tiles para Folium (ex: "OpenStreetMap", "CartoDB positron").
    """
    if not graph.nodes():
        print("Grafo está vazio. Nada para criar mapa interativo.")
        return

    node_latitudes = [data['latitude'] for node, data in graph.nodes(data=True) if 'latitude' in data]
    node_longitudes = [data['longitude'] for node, data in graph.nodes(data=True) if 'longitude' in data]

    if not node_latitudes or not node_longitudes:
        print("Nós não contêm informações de latitude/longitude suficientes.")
        return
    
    center_lat = sum(node_latitudes) / len(node_latitudes)
    center_lon = sum(node_longitudes) / len(node_longitudes)
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles=tile_provider)

    for node_name, data in graph.nodes(data=True):
        lat = data.get('latitude')
        lon = data.get('longitude')
        full_name = data.get('nome_completo', node_name)
        
        if lat is None or lon is None:
            continue

        linhas_na_parada = df_itinerarios[df_itinerarios['parada_nome'] == node_name]['numero_linha'].unique().tolist()
        linhas_str = ", ".join(linhas_na_parada) if linhas_na_parada else "Nenhuma linha principal associada"

        popup_html = f"""<b>Parada:</b> {node_name}<br>
                       <b>Endereço:</b> {full_name}<br>
                       <b>Latitude:</b> {lat:.5f}<br>
                       <b>Longitude:</b> {lon:.5f}<br>
                       <b>Linhas (EPT):</b> {linhas_str}"""
        
        popup = folium.Popup(popup_html, max_width=300)
        
        is_on_path = path_to_highlight and node_name in path_to_highlight
        marker_color = 'red' if is_on_path else 'blue'
        marker_radius = 8 if is_on_path else 5
        icon_type = 'info-sign' if is_on_path else 'bus' # Exemplo de ícones diferentes
        
        # Usar folium.Marker com ícones para mais variedade, ou CircleMarker para simplicidade
        # folium.Marker(
        #     location=[lat, lon],
        #     popup=popup,
        #     tooltip=node_name,
        #     icon=folium.Icon(color=marker_color, icon=icon_type, prefix='glyphicon')
        # ).add_to(m)
        folium.CircleMarker(
            location=[lat, lon],
            radius=marker_radius,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.7,
            popup=popup,
            tooltip=node_name 
        ).add_to(m)

    path_edges_set = set()
    if path_to_highlight and len(path_to_highlight) >=2:
        path_edges_set = set(zip(path_to_highlight[:-1], path_to_highlight[1:]))

    for u, v, edge_data in graph.edges(data=True):
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        
        if 'latitude' not in u_data or 'longitude' not in u_data or \
           'latitude' not in v_data or 'longitude' not in v_data:
            continue

        locs = [
            (u_data['latitude'], u_data['longitude']),
            (v_data['latitude'], v_data['longitude'])
        ]
        
        dist_km_val = edge_data.get('weight')
        dist_km_str = f"{dist_km_val:.2f} km" if isinstance(dist_km_val, (int, float)) else "N/A"
        linhas_passantes = ", ".join(edge_data.get('linhas_passantes', []))
        linha_principal = edge_data.get('linha', 'N/A')

        edge_popup_html = f"""<b>Trecho:</b> {u} → {v}<br>
                            <b>Distância:</b> {dist_km_str}<br>
                            <b>Linha Principal (neste trecho):</b> {linha_principal}<br>
                            <b>Todas as Linhas (neste trecho):</b> {linhas_passantes}"""
        edge_popup = folium.Popup(edge_popup_html, max_width=300)

        is_edge_on_path = (u,v) in path_edges_set
        line_color = 'red' if is_edge_on_path else '#555555' # Cinza mais escuro para arestas gerais
        line_weight = 4 if is_edge_on_path else 2.5
        line_opacity = 0.85 if is_edge_on_path else 0.6

        folium.PolyLine(
            locations=locs, 
            color=line_color, 
            weight=line_weight, 
            opacity=line_opacity,
            popup=edge_popup,
            tooltip=f"{u} → {v} ({dist_km_str})"
        ).add_to(m)

    # Adicionar controle de camadas para poder ligar/desligar tiles, se desejar mais de um
    # folium.TileLayer('CartoDB dark_matter', name='Modo Escuro', attr="CartoDB Dark Matter").add_to(m)
    # folium.TileLayer('Stamen Terrain', name='Relevo', attr="Stamen Terrain").add_to(m)
    # folium.LayerControl().add_to(m)

    try:
        m.save(map_filename)
        print(f"Mapa interativo salvo em '{map_filename}'")
        # Abrir o mapa no navegador padrão
        try:
            webbrowser.open('file://' + os.path.realpath(map_filename))
            print(f"Tentando abrir '{map_filename}' no navegador...")
        except Exception as e_wb:
            print(f"Não foi possível abrir o mapa no navegador automaticamente: {e_wb}")
            print(f"Por favor, abra o arquivo '{os.path.realpath(map_filename)}' manualmente.")

    except Exception as e:
        print(f"Erro ao salvar o mapa interativo: {e}") 