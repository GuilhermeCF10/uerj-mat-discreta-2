"""
Main script to scrape bus line and stop data from Moovit and save to CSV.

This script orchestrates the extraction of EPT bus line data from the Moovit website,
retrieves the stops for each line, and consolidates the data into a CSV file.
"""
import time
import pandas as pd # Importar pandas
import os # Adicionado para verificações de arquivo
import pickle # Para salvar/carregar o grafo NetworkX
import networkx as nx # Para type hinting e manipulação do grafo
import argparse # Adicionar import do argparse

# Importa as novas classes
from moovit_scraper import MoovitScraper
from data_exporter import DataExporter
from geocoder import GeoCoder # Importar GeoCoder
import graph_analysis as graph_analysis # Para gerar o mapa

# --- Funções de Cache para o Grafo NetworkX ---
# Estas funções são movidas para cá para serem usadas pelo AppController
def save_graph_to_cache(graph: nx.DiGraph, cache_path: str):
    """Salva o grafo NetworkX em um arquivo usando pickle."""
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump(graph, f, pickle.HIGHEST_PROTOCOL)
        print(f"Grafo salvo em cache em '{cache_path}'")
    except Exception as e:
        print(f"Erro ao salvar o grafo no cache '{cache_path}': {e}")

def load_graph_from_cache(cache_path: str, source_csv_path: str) -> nx.DiGraph | None:
    """
    Carrega o grafo NetworkX do cache se existir e for mais recente que o CSV de origem.
    Retorna o grafo carregado ou None.
    """
    if not os.path.exists(cache_path):
        print(f"(Cache do Grafo) Arquivo '{cache_path}' não encontrado.")
        return None
    
    if not os.path.exists(source_csv_path):
        print(f"(Cache do Grafo) Arquivo CSV de origem '{source_csv_path}' não encontrado. Cache do grafo invalidado.")
        return None
        
    try:
        cache_mod_time = os.path.getmtime(cache_path)
        csv_mod_time = os.path.getmtime(source_csv_path)
        
        if cache_mod_time > csv_mod_time:
            print(f"(Cache do Grafo) Carregando grafo do cache '{cache_path}' (válido)...")
            with open(cache_path, 'rb') as f:
                G = pickle.load(f)
            print("(Cache do Grafo) Grafo carregado com sucesso.")
            return G
        else:
            print(f"(Cache do Grafo) Cache '{cache_path}' desatualizado em relação a '{source_csv_path}'.")
            return None
    except Exception as e:
        print(f"(Cache do Grafo) Erro ao carregar/validar: {e}.")
        return None
# --- Fim das Funções de Cache ---

class AppController:
    """
    Controla o fluxo principal da aplicação de scraping de dados do Moovit.
    Orquestra o uso do scraper para coletar dados, geocodificá-los e do exporter para salvá-los.
    """
    # Constantes da Aplicação podem ser definidas aqui para fácil configuração
    EPT_LINES_URL = "https://moovitapp.com/index/pt-br/transporte_p%C3%BAblico-lines-Rio_de_Janeiro-322-1036555"
    CSV_RAW_FILENAME = "script/data/moovit_stops_raw.csv" # Cache para dados brutos
    CSV_GEOCODED_FILENAME = "script/data/moovit_stops_geocoded.csv" # Arquivo de dados geocodificados
    CSV_GEOCODED_FILTERED_FILENAME = "script/data/moovit_stops_geocoded_filtered.csv" # Arquivo de dados filtrados para Itaipuaçu
    CACHE_GRAFO_FILENAME = "script/cache/cached_moovit_graph.gpickle" # Cache para o grafo NetworkX
    MAP_HTML_FILENAME = "script/map_moovit_stops.html" # Nome do arquivo do mapa final
    MAP_HTML_FILTERED_FILENAME = "script/map_moovit_stops_itaipuacu.html" # Nome do mapa filtrado

    # Coordenadas do delimitador para Itaipuaçu (Recanto de Itaipuaçu até Restringa de Maricá, ate Inicio de São José do Imabssai e até Inoa)
    LAT_MIN_ITA, LAT_MAX_ITA = -22.990, -22.900
    LON_MIN_ITA, LON_MAX_ITA = -43.030, -42.870

    def __init__(self):
        """
        Inicializa o controlador da aplicação, instanciando scraper, exporter e geocoder.
        """
        self.scraper = MoovitScraper(sleep_duration=2.5) # sleep_duration pode ser ajustado aqui
        self.exporter = DataExporter()
        self.geocoder = GeoCoder(user_agent_suffix="MoovitMaricaScraper/1.0 (seuemail@example.com)", ) # Atualize com seu email
        self.all_stops_data_list = [] # Armazena a lista de dicionários de paradas

    def run(self, force_rescrape=False, force_regeocode=False):
        """
        Executa o processo completo de scraping, geocodificação e exportação de dados.
        Args:
            force_rescrape (bool): Se True, força o scraping dos dados mesmo que o cache raw exista.
            force_regeocode (bool): Se True, força a geocodificação mesmo que o cache geocodificado exista.
                                     Se True e force_rescrape é False, usará o cache raw (se existir) para re-geocodificar.
        """
        
        stops_df: pd.DataFrame | None = None # DataFrame para os dados
        geocoded_stops_df: pd.DataFrame | None = None # DataFrame para dados geocodificados

        # --- ETAPA DE SCRAPING E GEOCODIFICAÇÃO ---
        # 1. Verificar se o arquivo geocodificado final já existe e pode ser usado diretamente
        #    Se forçado a regeocodificar ou refazer scraping, ele será recriado.
        if not force_regeocode and not force_rescrape and os.path.exists(self.CSV_GEOCODED_FILENAME):
            print(f"Arquivo geocodificado final '{self.CSV_GEOCODED_FILENAME}' já existe. Tentando carregar para o mapa...")
            try:
                geocoded_stops_df = pd.read_csv(self.CSV_GEOCODED_FILENAME)
                print(f"Dados geocodificados carregados de '{self.CSV_GEOCODED_FILENAME}'. {len(geocoded_stops_df)} registros.")
            except Exception as e:
                print(f"Erro ao carregar '{self.CSV_GEOCODED_FILENAME}': {e}. Prosseguindo para possível recriação.")
                geocoded_stops_df = None # Garante que será recriado se a leitura falhar
        
        # Se os dados geocodificados não foram carregados (ou precisam ser recriados)
        if geocoded_stops_df is None:
            # 2. Tentar carregar do cache de dados brutos (para geocodificação)
            if not force_rescrape and os.path.exists(self.CSV_RAW_FILENAME):
                print(f"Arquivo de dados brutos '{self.CSV_RAW_FILENAME}' encontrado. Tentando carregar...")
                try:
                    stops_df = pd.read_csv(self.CSV_RAW_FILENAME)
                    print(f"Dados brutos carregados com sucesso do cache. {len(stops_df)} registros.")
                except pd.errors.EmptyDataError:
                    print(f"Cache de dados brutos '{self.CSV_RAW_FILENAME}' está vazio. Prosseguindo com scraping.")
                    stops_df = None
                except Exception as e:
                    print(f"Erro ao carregar dados brutos do cache '{self.CSV_RAW_FILENAME}': {e}")
                    print("Prosseguindo com o scraping.")
                    stops_df = None
            
            # 3. Scraping (se não carregou do cache raw ou se forçado)
            if stops_df is None or force_rescrape:
                if force_rescrape:
                    print("Forçando o re-scraping dos dados...")
                elif stops_df is None: 
                    print("Nenhum cache de dados brutos válido encontrado. Iniciando scraping...")

                print(f"Buscando página principal das linhas EPT: {self.EPT_LINES_URL}")
                main_page_html = self.scraper._get_html_content(self.EPT_LINES_URL)

                if not main_page_html:
                    print("Não foi possível obter a página principal das linhas. Encerrando.")
                    return

                print("Extraindo links das linhas...")
                lines = self.scraper.extract_line_links(main_page_html)

                if not lines:
                    print("Nenhuma linha encontrada para processar. Verifique os seletores em MoovitScraper.")
                    return

                print(f"Encontradas {len(lines)} linhas para processar.")
                
                # Para testes, pode-se descomentar a linha abaixo para processar um subconjunto:
                # lines_to_process = lines[:2] 
                lines_to_process = lines

                self.all_stops_data_list = [] # Resetar lista antes de um novo scraping
                print(f"\nIniciando processamento para {len(lines_to_process)} linhas...")
                for i, line_info in enumerate(lines_to_process):
                    line_code = line_info.get('numero_linha')
                    line_name = line_info.get('nome_linha')
                    line_url = line_info.get('url') # URL é obrigatória

                    # Prepara o nome da linha para exibição no log
                    line_print_name = line_code if line_code else "(Sem Código)"
                    if line_name:
                        line_print_name += f" ({line_name})"
                    
                    if not line_url:
                        print(f"  AVISO: URL da linha não encontrada para o item {i+1}. Linha ignorada: {line_info}")
                        continue

                    print(f"\nProcessando linha {i + 1}/{len(lines_to_process)}: {line_print_name} ({line_url})")

                    # Busca o HTML da página de detalhes da linha
                    line_page_html = self.scraper._get_html_content(line_url)

                    if line_page_html:
                        # Extrai as paradas da página da linha
                        stops = self.scraper.extract_stops_from_line_page(
                            html_content=line_page_html,
                            line_number_ref=line_code,
                            line_name_ref=line_name,
                            line_url_ref=line_url
                        )
                        if stops:
                            self.all_stops_data_list.extend(stops)
                            print(f"  -> Encontradas {len(stops)} paradas para {line_print_name}.")
                        else:
                            print(f"  -> Nenhuma parada encontrada ou extraída para {line_print_name}.")

                        # Pausa entre o processamento de linhas para não sobrecarregar o servidor
                        if i < len(lines_to_process) - 1:
                            print(f"  Aguardando {self.scraper.sleep_duration}s...")
                            time.sleep(self.scraper.sleep_duration)
                    else:
                        print(f"  ERRO: Não foi possível obter o conteúdo para a linha {line_print_name} ({line_url}).")

                # Exporta os dados coletados para CSV
                if not self.all_stops_data_list:
                    print("\nNenhum dado de parada foi coletado de nenhuma linha. Arquivos e mapa não serão criados.")
                    return

                print("\nConvertendo dados de paradas coletados para DataFrame...")
                stops_df = pd.DataFrame(self.all_stops_data_list)
                
                if not stops_df.empty:
                    try:
                        print(f"Salvando dados brutos em '{self.CSV_RAW_FILENAME}'...")
                        self.exporter.export_to_csv(stops_df, self.CSV_RAW_FILENAME, expected_columns=stops_df.columns.tolist())
                        print("Dados brutos salvos com sucesso.")
                    except Exception as e:
                        print(f"Erro ao salvar dados brutos no cache '{self.CSV_RAW_FILENAME}': {e}")
                else:
                    print("Nenhum dado de parada coletado, cache de dados brutos não será salvo.")
                    return 
                
                if stops_df is None or stops_df.empty:
                    print("DataFrame de paradas está vazio após scraping/cache. Não é possível geocodificar.")
                    return 

            # 4. Geocodificação (aplicada a stops_df)
            print("\nIniciando geocodificação das paradas...")
            print("Verificando stops_df antes da geocodificação:")
            print(stops_df.head())
            print(f"Shape de stops_df: {stops_df.shape}")
            print(f"Colunas em stops_df: {stops_df.columns.tolist()}")
            
            geocoded_stops_df = self.geocoder.add_coordinates_to_dataframe(stops_df.copy(), stop_name_column='nome_parada', service="google")
            
            expected_columns_export = [
                'numero_linha', 'nome_linha', 'url_linha', 'sentido', 'ordem_parada', 'nome_parada',
                'latitude', 'longitude', 'endereco_geocodificado'
            ]
            print(f"\nExportando dados geocodificados para '{self.CSV_GEOCODED_FILENAME}'...")
            self.exporter.export_to_csv(geocoded_stops_df, self.CSV_GEOCODED_FILENAME, expected_columns_export)
            
        # --- FIM DA ETAPA DE SCRAPING E GEOCODIFICAÇÃO ---

        # --- ETAPA DE GERAÇÃO DO MAPA ---
        # Esta seção agora está corretamente posicionada para ser executada 
        # após geocoded_stops_df ser definido (carregado ou criado).
        if geocoded_stops_df is not None and not geocoded_stops_df.empty:
            print("\n--- Fase de Geração do Mapa Interativo --- ")
            self._generate_interactive_map(geocoded_stops_df)
        elif geocoded_stops_df is None:
            print("Dados geocodificados não estão disponíveis. Mapa não será gerado.")
        else: # DataFrame está vazio
            print("DataFrame de dados geocodificados está vazio. Mapa não será gerado.")

        print("\nProcesso concluído.") # Mensagem final mais genérica

    def _generate_interactive_map(self, df_geocoded_data_for_map: pd.DataFrame):
        """
        Gera o mapa interativo HTML usando os dados geocodificados fornecidos.
        Esta função assume que df_geocoded_data_for_map é o DataFrame após a geocodificação,
        com colunas como 'nome_parada', 'latitude', 'longitude', 'numero_linha', etc.
        """
        print(f"Preparando dados para o grafo e mapa a partir de '{self.CSV_GEOCODED_FILENAME}' (usando dados em memória).")

        # Mapear colunas para os nomes esperados por graph_analysis.py
        mapeamento_colunas_graph_analysis = {
            'nome_parada': 'parada_nome',
            # 'numero_linha': 'linha_codigo',  # REMOVIDO: manter numero_linha
            # As outras colunas como 'latitude', 'longitude', 'endereco_geocodificado',
            # 'sentido', 'ordem_parada' devem ter nomes consistentes se vierem de expected_columns.
        }
        df_para_grafo_e_mapa = df_geocoded_data_for_map.rename(columns=mapeamento_colunas_graph_analysis)

        # Validar colunas necessárias para o grafo
        colunas_necessarias_grafo = ['parada_nome', 'latitude', 'longitude', 'numero_linha', 'sentido', 'ordem_parada']
        faltando_grafo = [col for col in colunas_necessarias_grafo if col not in df_para_grafo_e_mapa.columns]
        if faltando_grafo:
            print(f"ERRO (Mapa): Colunas necessárias para criar o grafo não encontradas: {faltando_grafo}")
            print(f"Colunas disponíveis: {df_para_grafo_e_mapa.columns.tolist()}")
            print("Geração do mapa cancelada.")
            return

        # Tentar carregar o grafo do cache
        G_moovit: nx.DiGraph | None = load_graph_from_cache(self.CACHE_GRAFO_FILENAME, self.CSV_GEOCODED_FILENAME)

        if G_moovit is None:
            print("(Mapa) Construindo o grafo de transporte...")
            G_moovit = graph_analysis.create_transport_graph(df_para_grafo_e_mapa)
            
            if G_moovit is not None and G_moovit.number_of_nodes() > 0:
                save_graph_to_cache(G_moovit, self.CACHE_GRAFO_FILENAME)
            elif G_moovit is None or G_moovit.number_of_nodes() == 0:
                print("(Mapa) Falha ao criar o grafo ou o grafo está vazio. Mapa não será gerado.")
                return
        
        if G_moovit is None or G_moovit.number_of_nodes() == 0:
             print("(Mapa) O grafo está vazio ou não pôde ser construído/carregado. Mapa não será gerado.")
             return

        print(f"(Mapa) Grafo completo carregado/criado com {G_moovit.number_of_nodes()} nós e {G_moovit.number_of_edges()} arestas.")

        # --- Filtragem para Itaipuaçu ---
        print("\n--- Aplicando filtro para a região de Itaipuaçu ---")
        
        def inside_bbox(node_data):
            # NetworkX armazena lon, lat em 'pos', mas também temos 'latitude' e 'longitude' diretamente
            lat = node_data.get('latitude')
            lon = node_data.get('longitude')
            if lat is None or lon is None:
                # Tentar obter de 'pos' se disponível e 'latitude'/'longitude' não estiverem
                pos = node_data.get('pos') # Espera-se (lon, lat)
                if pos and isinstance(pos, tuple) and len(pos) == 2:
                    lon, lat = pos[0], pos[1] # Ordem em 'pos' é (lon, lat)
                else:
                    return False # Não há dados de coordenadas suficientes
            return (self.LAT_MIN_ITA <= lat <= self.LAT_MAX_ITA and
                    self.LON_MIN_ITA <= lon <= self.LON_MAX_ITA)

        ita_nodes = [node_name for node_name, data in G_moovit.nodes(data=True) if inside_bbox(data)]
        
        if not ita_nodes:
            print("(Mapa) Nenhum nó encontrado dentro do delimitador de Itaipuaçu. Mapa filtrado e CSV não serão gerados.")
            # Ainda assim, podemos gerar o mapa completo se desejado, ou parar aqui.
            # Por ora, vamos gerar o mapa completo como fallback.
            # Se quiser evitar isso, adicione um 'return' aqui.
            print("(Mapa) Gerando mapa completo como fallback, pois a área filtrada é vazia.")
            G_para_mapa = G_moovit
            df_para_mapa_final = df_para_grafo_e_mapa
            map_filename_final = self.MAP_HTML_FILENAME
        else:
            G_itaipuacu = G_moovit.subgraph(ita_nodes).copy()
            print(f"(Mapa) Subgrafo de Itaipuaçu criado com {G_itaipuacu.number_of_nodes()} nós e {G_itaipuacu.number_of_edges()} arestas.")

            # Filtrar o DataFrame para conter apenas as paradas do subgrafo de Itaipuaçu
            # Usamos 'parada_nome' que é a chave dos nós no grafo
            df_geocoded_filtered_ita = df_para_grafo_e_mapa[df_para_grafo_e_mapa['parada_nome'].isin(ita_nodes)].copy()
            
            if not df_geocoded_filtered_ita.empty:
                print(f"(Mapa) Salvando dados geocodificados filtrados para Itaipuaçu em '{self.CSV_GEOCODED_FILTERED_FILENAME}'...")
                try:
                    # Usar as colunas originais esperadas para manter a consistência
                    expected_columns_export = [
                        'numero_linha', 'nome_linha', 'url_linha', 'sentido', 'ordem_parada', 'nome_parada',
                        'latitude', 'longitude', 'endereco_geocodificado'
                    ]
                    # Garantir que apenas colunas existentes no df filtrado sejam pedidas
                    cols_to_export = [col for col in expected_columns_export if col in df_geocoded_filtered_ita.columns]
                    
                    self.exporter.export_to_csv(df_geocoded_filtered_ita, self.CSV_GEOCODED_FILTERED_FILENAME, expected_columns=cols_to_export)
                    print(f"(Mapa) Dados filtrados salvos em '{self.CSV_GEOCODED_FILTERED_FILENAME}'. {len(df_geocoded_filtered_ita)} registros.")
                except Exception as e:
                    print(f"(Mapa) Erro ao salvar CSV filtrado: {e}")
            else:
                print("(Mapa) DataFrame filtrado para Itaipuaçu está vazio. CSV não será salvo.")
            
            G_para_mapa = G_itaipuacu
            df_para_mapa_final = df_geocoded_filtered_ita # Usar o DataFrame filtrado para o mapa
            map_filename_final = self.MAP_HTML_FILTERED_FILENAME

        if G_para_mapa is not None and G_para_mapa.number_of_nodes() > 0:
            if df_para_mapa_final.empty and G_para_mapa == G_itaipuacu : # Se o grafo filtrado existe mas o df ficou vazio
                print("(Mapa) Atenção: O grafo filtrado de Itaipuaçu tem nós, mas o DataFrame correspondente está vazio.")
                print("(Mapa) Verifique a consistência dos nomes das paradas entre o grafo e o DataFrame.")
                print("(Mapa) O mapa de Itaipuaçu será gerado, mas pode não ter todos os popups/informações de aresta corretos se depender do DataFrame.")
                # Para o mapa, precisamos de df_para_grafo_e_mapa (original) para detalhes das linhas, mesmo que filtrado
                # A função create_interactive_map usa o df para buscar linhas por parada_nome.
                # Se df_para_mapa_final está vazio, ele não encontrará informações.
                # Uma opção é passar df_para_grafo_e_mapa, e a função create_interactive_map internamente fará a busca.
                # Ou garantir que df_para_mapa_final contenha os dados necessários.
                # Por simplicidade, vamos usar o df_geocoded_filtered_ita que deve ser o correto.
                # Se ele estiver vazio, o mapa será gerado mas as informações de parada podem ser limitadas.


            print(f"(Mapa) Gerando mapa interativo HTML em '{map_filename_final}'...")
            
            graph_analysis.create_interactive_map(
                G_para_mapa, 
                df_para_mapa_final if not df_para_mapa_final.empty else df_para_grafo_e_mapa, # Fallback para df original se o filtrado estiver vazio e G filtrado não.
                path_to_highlight=None, 
                map_filename=map_filename_final
            )
            print("(Mapa) Processo de criação do mapa concluído.")
        else:
             print("(Mapa) O grafo final para o mapa está vazio ou não pôde ser construído. Mapa não será gerado.")

if __name__ == "__main__":
    # --- Configuração do ArgumentParser ---
    parser = argparse.ArgumentParser(description="Executa o scraper de dados de ônibus do Moovit, geocodifica e gera um mapa.")
    parser.add_argument(
        "--force-rescrape",
        action="store_true",  # Define como uma flag booleana, True se presente
        help="Força o re-scraping dos dados do Moovit, mesmo que existam caches de dados brutos."
    )
    parser.add_argument(
        "--force-regeocode",
        action="store_true",  # Define como uma flag booleana, True se presente
        help="Força a re-geocodificação dos dados, mesmo que existam caches de dados geocodificados. Se usado sem --force-rescrape, tentará usar o cache de dados brutos para re-geocodificar."
    )
    args = parser.parse_args()

    # --- Execução do Controlador Principal ---
    print("Iniciando o AppController...")
    controller = AppController()
    
    # Passa os argumentos da linha de comando para o método run
    controller.run(force_rescrape=args.force_rescrape, force_regeocode=args.force_regeocode)

    print("\n--- Fim da Execução do Script Main ---") 