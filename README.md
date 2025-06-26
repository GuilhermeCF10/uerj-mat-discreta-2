# Projeto de Análise de Rede de Transporte Público de Maricá

Este projeto tem como objetivo realizar a coleta, processamento e análise de dados das linhas e paradas de ônibus da Empresa Pública de Transportes (EPT) de Maricá, RJ. O sistema automatiza o scraping de dados do site Moovit, realiza a geocodificação dos endereços das paradas, constrói um grafo da rede de transporte e gera um mapa interativo.

Adicionalmente, o sistema permite filtrar os dados para focar em sub-regiões específicas (ex: Itaipuaçu), possibilitando análises mais detalhadas e estudos de caso, como otimização de rotas e cobertura de vias principais nessas áreas.

**Para uma documentação técnica detalhada sobre a arquitetura interna, fluxo de dados, estrutura de arquivos completa e as análises específicas derivadas, consulte o [README detalhado do diretório script](script/README.md).**

## Funcionalidades Principais

1.  **Scraping de Dados:**
    *   Coleta informações sobre as linhas de ônibus da EPT (códigos, nomes e URLs de detalhe) a partir de uma URL principal do Moovit.
    *   Para cada linha, acessa sua página de detalhes e extrai a sequência de paradas em cada sentido, incluindo nome da parada, ordem e sentido.
    *   Os dados brutos coletados são salvos em `script/data/moovit_stops_raw.csv`.

2.  **Geocodificação:**
    *   Utiliza os nomes das paradas coletados para obter suas coordenadas geográficas (latitude e longitude).
    *   Prioritariamente, usa a API de Geocodificação do Google, otimizando as chamadas para processar apenas endereços únicos e utilizando componentes geográficos (cidade, estado, país) para maior precisão.
    *   Os dados enriquecidos com as coordenadas são salvos em `script/data/moovit_stops_geocoded.csv`.
    *   Quando a filtragem por sub-região é aplicada (ex: Itaipuaçu), um arquivo como `script/data/moovit_stops_geocoded_filtered.csv` é gerado.

3.  **Criação de Grafo da Rede:**
    *   A partir dos dados geocodificados (completos ou filtrados), constrói um grafo direcionado (`NetworkX.DiGraph`) onde:
        *   **Nós**: Representam as paradas de ônibus únicas, com atributos de posição (latitude, longitude) e nome completo.
        *   **Arestas**: Representam conexões diretas entre paradas sequenciais em uma mesma linha e sentido, com atributos como distância (calculada geodésicamente) e a linha de ônibus correspondente.
    *   O grafo construído pode ser salvo em cache (`script/cache/cached_moovit_graph.gpickle`) para agilizar execuções futuras.

4.  **Geração de Mapa Interativo:**
    *   Utiliza o grafo da rede e os dados geocodificados para gerar mapas HTML interativos usando a biblioteca Folium.
    *   São gerados:
        *   `script/map_moovit_stops.html`: Mapa da rede completa de Maricá.
        *   `script/map_moovit_stops_itaipuacu.html` (ou similar): Mapa da rede filtrada para a sub-região especificada.
    *   Análises específicas em `script/tests/` também geram seus próprios mapas (ex: `script/tests/otimizacao/map.html`).

5.  **Cache:**
    *   O sistema implementa mecanismos de cache para os dados brutos de scraping, dados geocodificados e para o grafo da rede, evitando reprocessamento desnecessário em execuções subsequentes.
    *   Flags podem ser usadas para forçar o re-scraping (`--force-rescrape`) ou a re-geocodificação (`--force-regeocode`).

## Estrutura do Projeto e Módulos Principais (dentro de `script/`)

O núcleo da lógica de processamento reside no diretório `script/`:
*   `main.py`: Script principal que orquestra todo o fluxo da aplicação, desde o scraping até a geração do mapa. Contém a classe `AppController`.
*   `moovit_scraper.py`: Responsável pelo scraping dos dados do site Moovit. Contém a classe `MoovitScraper`.
*   `geocoder.py`: Encarregado da geocodificação dos endereços das paradas. Contém a classe `GeoCoder`.
*   `data_exporter.py`: Lida com a exportação dos dados processados para arquivos CSV. Contém a classe `DataExporter`.
*   `graph_analysis.py`: Contém as funções para criar o grafo da rede de transporte e gerar os mapas com Folium.
*   `tests/`: Subdiretório contendo scripts para análises mais específicas e aprofundadas sobre subconjuntos de dados (ex: otimização de rotas em Itaipuaçu). Cada análise possui seu próprio `main.py`, `readme.md` e mapa resultante.
*   `requirements.txt`: Lista as dependências Python do projeto.
*   `setup.sh`: Script de shell para configuração inicial do ambiente e instalação de dependências.

## Como Executar (Visão Geral)

1.  Navegue até o diretório `script/`.
2.  Configure as dependências: `bash setup.sh` (cria diretórios e instala pacotes de `requirements.txt`).
3.  Garantir que uma chave da API do Google Maps esteja configurada como variável de ambiente `GOOGLE_MAPS_API_KEY`.
4.  Executar o script principal a partir do diretório `script/`: `python3 main.py`.
    *   Use flags como `--force-rescrape` ou `--force-regeocode` conforme necessário.

O script tentará carregar dados de caches existentes. Se não encontrados ou se as flags de forçar reprocessamento estiverem ativas, ele executará as etapas de scraping e/ou geocodificação conforme necessário antes de gerar o grafo e os mapas.
Consulte o [README detalhado do diretório script](script/README.md) para mais informações sobre a execução e as análises específicas.
