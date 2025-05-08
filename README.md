# Projeto de Análise de Rede de Transporte Público de Maricá

Este projeto tem como objetivo realizar a coleta, processamento e análise de dados das linhas e paradas de ônibus da Empresa Pública de Transportes (EPT) de Maricá, RJ. O sistema automatiza o scraping de dados do site Moovit, realiza a geocodificação dos endereços das paradas, constrói um grafo da rede de transporte e gera um mapa interativo.

## Funcionalidades Principais

1.  **Scraping de Dados:**
    *   Coleta informações sobre as linhas de ônibus da EPT (códigos, nomes e URLs de detalhe) a partir de uma URL principal do Moovit.
    *   Para cada linha, acessa sua página de detalhes e extrai a sequência de paradas em cada sentido, incluindo nome da parada, ordem e sentido.
    *   Os dados brutos coletados são salvos em `moovit_stops_raw.csv`.

2.  **Geocodificação:**
    *   Utiliza os nomes das paradas coletados para obter suas coordenadas geográficas (latitude e longitude).
    *   Prioritariamente, usa a API de Geocodificação do Google, otimizando as chamadas para processar apenas endereços únicos e utilizando componentes geográficos (cidade, estado, país) para maior precisão.
    *   Os dados enriquecidos com as coordenadas são salvos em `moovit_stops_geocoded.csv`.

3.  **Criação de Grafo da Rede:**
    *   A partir dos dados geocodificados, constrói um grafo direcionado (`NetworkX.DiGraph`) onde:
        *   **Nós**: Representam as paradas de ônibus únicas, com atributos de posição (latitude, longitude) e nome completo.
        *   **Arestas**: Representam conexões diretas entre paradas sequenciais em uma mesma linha e sentido, com atributos como distância (calculada geodésicamente) e a linha de ônibus correspondente.
    *   O grafo construído pode ser salvo em cache (`cached_moovit_graph.gpickle`) para agilizar execuções futuras.

4.  **Geração de Mapa Interativo:**
    *   Utiliza o grafo da rede e os dados geocodificados para gerar um mapa HTML interativo (`map_moovit_stops.html`) usando a biblioteca Folium.
    *   O mapa exibe as paradas e as conexões entre elas, permitindo uma visualização da rede de transporte.

5.  **Cache:**
    *   O sistema implementa mecanismos de cache para os dados brutos de scraping, dados geocodificados e para o grafo da rede, evitando reprocessamento desnecessário em execuções subsequentes.
    *   Flags podem ser usadas para forçar o re-scraping (`force_rescrape`) ou a re-geocodificação (`force_regeocode`).

## Estrutura do Projeto e Módulos Principais

*   `moovit_main.py`: Script principal que orquestra todo o fluxo da aplicação, desde o scraping até a geração do mapa. Contém a classe `AppController`.
*   `moovit_scraper.py`: Responsável pelo scraping dos dados do site Moovit. Contém a classe `MoovitScraper`.
*   `geocoder.py`: Encarregado da geocodificação dos endereços das paradas. Contém a classe `GeoCoder`.
*   `data_exporter.py`: Lida com a exportação dos dados processados para arquivos CSV. Contém a classe `DataExporter`.
*   `graph_analysis.py`: Contém as funções para criar o grafo da rede de transporte, calcular distâncias, encontrar caminhos e gerar os mapas (tanto estáticos com Matplotlib/Contextily quanto interativos com Folium).
*   `requirements.txt`: Lista as dependências Python do projeto.
*   `setup.sh`: Script de shell (provavelmente para configuração inicial do ambiente ou instalação de dependências).

## Como Executar (Visão Geral)

1.  Configurar as dependências listadas em `requirements.txt` (idealmente em um ambiente virtual).
2.  Garantir que uma chave da API do Google Maps esteja configurada como variável de ambiente (`GOOGLE_MAPS_API_KEY`). Isso é necessário para a etapa de geocodificação.
3.  Executar o script principal: `python3 moovit_main.py`.

O script tentará carregar dados de caches existentes. Se não encontrados ou se as flags de forçar reprocessamento estiverem ativas, ele executará as etapas de scraping e/ou geocodificação conforme necessário antes de gerar o grafo e o mapa.
