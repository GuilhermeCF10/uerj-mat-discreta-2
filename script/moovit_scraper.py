import re
import time
import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin

class MoovitScraper:
    """
    Classe responsável por realizar o scraping de dados de linhas e paradas
    de ônibus do site Moovit.
    """
    BASE_URL = "https://moovitapp.com"

    def __init__(self, sleep_duration: float = 2.5, retries: int = 3, request_delay: int = 5):
        """
        Inicializa o scraper.

        Args:
            sleep_duration: Duração (em segundos) da pausa entre requisições de
                            páginas de detalhes de linhas.
            retries: Número de tentativas para buscar uma URL.
            request_delay: Atraso (em segundos) entre tentativas de requisição.
        """
        self.sleep_duration = sleep_duration
        self.retries = retries
        self.request_delay = request_delay
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def _get_html_content(self, url: str) -> str | None:
        """
        Faz uma requisição GET para a URL e retorna o conteúdo HTML.
        Esta lógica foi movida de moovit_utils.py.

        Args:
            url: A URL para buscar.

        Returns:
            O conteúdo HTML da página como string, ou None se a requisição falhar
            após todas as tentativas.
        """
        for attempt in range(self.retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=20)
                response.raise_for_status()  # Levanta HTTPError para respostas ruins (4xx ou 5xx)
                return response.text
            except requests.Timeout:
                print(f"Timeout na tentativa {attempt + 1} para {url}")
            except requests.RequestException as e:
                print(f"Erro na requisição para {url} (tentativa {attempt + 1}): {e}")

            if attempt < self.retries - 1:
                print(f"Aguardando {self.request_delay} segundos antes da próxima tentativa...")
                time.sleep(self.request_delay)
        print(f"Falha ao buscar {url} após {self.retries} tentativas.")
        return None

    def extract_line_links(self, html_content: str) -> list[dict]:
        """
        Extrai códigos de linha, nomes descritivos e links da página principal de linhas.
        Esta lógica foi movida e adaptada de get_moovit_stations.py.

        Args:
            html_content: O conteúdo HTML da página que lista múltiplas linhas de ônibus.

        Returns:
            Uma lista de dicionários, onde cada dicionário contém:
            - "numero_linha": O código da linha (ex: "E06").
            - "nome_linha": O nome descritivo completo (ex: "Centro - Espraiado").
            - "url": A URL absoluta para a página de detalhes da linha.
        """
        if not html_content:
            print("Conteúdo HTML está vazio. Não é possível extrair links de linhas.")
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        line_links_data = []
        processed_urls = set()

        selectors_to_try = [
            'ul.lines-list li a[href*="/transporte_p%C3%BAblico-line-"]',
            'ul.agency-lines-group li a[href*="/transporte_p%C3%BAblico-line-"]',
            'div.lines_container a.line-item',
            'a.line-item'
        ]

        line_link_elements = []
        for selector in selectors_to_try:
            elements = soup.select(selector)
            if elements:
                print(f"Encontrados elementos de link de linha usando o seletor: {selector}")
                line_link_elements = elements
                break

        if not line_link_elements:
            print("Nenhum elemento de link de linha encontrado com os seletores testados.")
            return []

        for link_tag in line_link_elements:
            if not isinstance(link_tag, Tag):
                continue

            line_code_from_url = None
            descriptive_name_from_html = None

            href_val = link_tag.get('href')
            partial_href = href_val if isinstance(href_val, str) else (href_val[0] if isinstance(href_val, list) and href_val else None)

            if not partial_href:
                continue

            line_detail_page_url = urljoin(self.BASE_URL, partial_href)

            url_match = re.search(r"line-([a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*)-Rio_de_Janeiro", line_detail_page_url)
            if url_match and url_match.group(1):
                line_code_from_url = url_match.group(1).upper()

            h2_tag_for_desc = None
            div_line_title_in_link = link_tag.find("div", class_="line-title")
            if div_line_title_in_link and isinstance(div_line_title_in_link, Tag):
                h2_candidate = div_line_title_in_link.find("h2", class_="title")
                if h2_candidate and isinstance(h2_candidate, Tag):
                    h2_tag_for_desc = h2_candidate
            
            if not h2_tag_for_desc and link_tag.parent:
                parent_element = link_tag.parent
                if parent_element and isinstance(parent_element, Tag): # Verificação adicional
                    div_line_title_in_parent = parent_element.find("div", class_="line-title")
                    if div_line_title_in_parent and isinstance(div_line_title_in_parent, Tag):
                        h2_candidate_parent = div_line_title_in_parent.find("h2", class_="title")
                        if h2_candidate_parent and isinstance(h2_candidate_parent, Tag):
                            h2_tag_for_desc = h2_candidate_parent
                
            if h2_tag_for_desc:
                desc_text_from_h2 = h2_tag_for_desc.get_text(strip=True)
                if desc_text_from_h2:
                    cleaned_desc = desc_text_from_h2.replace("\\\\n", " ").strip() # Corrigido para \\n
                    descriptive_name_from_html = " ".join(cleaned_desc.split()) if cleaned_desc else None

            if not descriptive_name_from_html:
                span_text_candidate = None
                spans_in_link = link_tag.find_all('span')
                for span_node in spans_in_link:
                    current_span_text = span_node.get_text(strip=True)
                    if current_span_text and (not line_code_from_url or current_span_text.lower() != line_code_from_url.lower()):
                        span_text_candidate = current_span_text
                        break 
                
                raw_descriptive_text = None
                if span_text_candidate:
                    raw_descriptive_text = span_text_candidate
                else: 
                    raw_descriptive_text = link_tag.get_text(strip=True, separator=" ")
                    if line_code_from_url and raw_descriptive_text:
                        code_pattern = re.compile(re.escape(line_code_from_url), re.IGNORECASE)
                        temp_desc = code_pattern.sub("", raw_descriptive_text).strip()
                        temp_desc = temp_desc.replace(f"Linha ", "", 1).strip()
                        if temp_desc and temp_desc.lower() != line_code_from_url.lower():
                            raw_descriptive_text = temp_desc
                        elif not temp_desc or temp_desc.lower() == line_code_from_url.lower():
                            raw_descriptive_text = None
                
                if raw_descriptive_text:
                    cleaned_name = raw_descriptive_text.replace("\\\\n", " ").strip() # Corrigido para \\n
                    descriptive_name_from_html = " ".join(cleaned_name.split()) if cleaned_name else None
                    if line_code_from_url and descriptive_name_from_html and descriptive_name_from_html.lower() == line_code_from_url.lower():
                        descriptive_name_from_html = None

            final_numero_linha = line_code_from_url
            final_nome_linha = descriptive_name_from_html

            primary_identifier = final_numero_linha if final_numero_linha else final_nome_linha
            if not primary_identifier or not primary_identifier.strip():
                continue

            if len(primary_identifier.strip()) > 150 and primary_identifier == final_nome_linha:
                print(f"  AVISO: Nome da linha '{primary_identifier.strip()[:70]}...' parece excessivamente longo. Verifique a extração para {line_detail_page_url}")

            if line_detail_page_url not in processed_urls:
                if final_numero_linha and final_nome_linha and final_nome_linha.lower() == final_numero_linha.lower():
                    final_nome_linha = None
                    
                line_entry = {
                    "numero_linha": final_numero_linha.strip() if final_numero_linha else None,
                    "nome_linha": final_nome_linha.strip() if final_nome_linha else None,
                    "url": line_detail_page_url
                }
                line_links_data.append(line_entry)
                processed_urls.add(line_detail_page_url)
        
        if not line_links_data:
            print("Lista final de links de linhas está vazia após o processamento de todos os elementos.")
            
        final_lines_deduplicated = []
        seen_identifiers = set()
        
        def sort_key(item):
            num = item.get("numero_linha")
            name = item.get("nome_linha")
            url_len = len(item['url'])
            if num:
                return (0, num, url_len) 
            return (1, name if name else "", url_len)
            
        for line_item in sorted(line_links_data, key=sort_key):
            identifier_for_dedup = line_item.get("numero_linha") or line_item.get("nome_linha")
            if identifier_for_dedup and identifier_for_dedup not in seen_identifiers:
                final_lines_deduplicated.append(line_item)
                seen_identifiers.add(identifier_for_dedup)
        return final_lines_deduplicated

    def extract_stops_from_line_page(self, html_content: str,
                                     line_number_ref: str | None,
                                     line_name_ref: str | None,
                                     line_url_ref: str) -> list[dict]:
        """
        Extrai paradas de ônibus de uma página individual de detalhes da linha.
        Esta lógica foi movida e adaptada de get_moovit_bus_stops.py.

        Args:
            html_content: O conteúdo HTML da página de detalhes da linha.
            line_number_ref: O código/número da linha (ex: "E06").
            line_name_ref: O nome descritivo da linha (ex: "Centro - Espraiado").
            line_url_ref: A URL da página da linha (para contexto em logs).

        Returns:
            Uma lista de dicionários, cada um representando uma parada de ônibus com
            as chaves: "numero_linha", "nome_linha", "url_linha", "sentido",
            "ordem_parada", "nome_parada".
        """
        if not html_content:
            print(f"Conteúdo HTML está vazio para a linha {line_number_ref or line_name_ref} em {line_url_ref}")
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        stops_data = []

        direction_wrappers = soup.find_all("div", class_="stops-wrapper")
        if not direction_wrappers:
            print(f"Nenhum 'div.stops-wrapper' encontrado para a linha {line_number_ref or line_name_ref} em {line_url_ref}.")
            return []

        print(f"  Encontrados {len(direction_wrappers)} blocos de direção ('div.stops-wrapper').")
        for wrapper_div in direction_wrappers:
            if not isinstance(wrapper_div, Tag):
                continue

            header_div = wrapper_div.find("div", class_="stops-header")
            current_direction_name = "Direção Desconhecida"
            if header_div and isinstance(header_div, Tag):
                h2_tag = header_div.find("h2")
                if h2_tag and isinstance(h2_tag, Tag):
                    direction_text = h2_tag.get_text(strip=True)
                    if "Sentido: " in direction_text:
                        current_direction_name = direction_text.split("Sentido: ", 1)[1].split("(", 1)[0].strip()
                    elif direction_text: # Fallback se "Sentido: " não estiver presente
                        current_direction_name = direction_text.split("(", 1)[0].strip()
                    print(f"    Processando direção: {current_direction_name}")
                else:
                    print(f"      Tag H2 para o título da direção não encontrada em div.stops-header para {line_url_ref}")
            else:
                print(f"      Div de cabeçalho da direção (div.stops-header) não encontrado para {line_url_ref}.")

            stops_list_ul = wrapper_div.select_one("ul[class*='stops-list']")
            if not stops_list_ul or not isinstance(stops_list_ul, Tag):
                print(f"      Lista de paradas (ul[class*='stops-list']) não encontrada para a direção '{current_direction_name}' em {line_url_ref}")
                continue

            stop_order_counter = 1
            stop_items_li = stops_list_ul.find_all("li", class_="stop-container")
            print(f"      Encontrados {len(stop_items_li)} itens de parada (li.stop-container) para '{current_direction_name}'.")

            for stop_li in stop_items_li:
                if not isinstance(stop_li, Tag):
                    continue

                stop_wrapper_div = stop_li.find("div", class_="stop-wrapper")
                if stop_wrapper_div and isinstance(stop_wrapper_div, Tag):
                    stop_name_tag = stop_wrapper_div.find("h3")
                    if stop_name_tag and isinstance(stop_name_tag, Tag):
                        stop_name = stop_name_tag.get_text(strip=True)
                        if stop_name:
                            stops_data.append({
                                "numero_linha": line_number_ref,
                                "nome_linha": line_name_ref,
                                "url_linha": line_url_ref,
                                "sentido": current_direction_name,
                                "ordem_parada": stop_order_counter,
                                "nome_parada": stop_name
                            })
                            stop_order_counter += 1
                        # else:
                        #     print(f"      Nome da parada vazio dentro da tag h3: {stop_name_tag.prettify()}")
                    # else:
                    #     print(f"      Tag h3 do nome da parada não encontrada em: {stop_wrapper_div.prettify()}")
                # else:
                #     print(f"      Div wrapper da parada não encontrado em: {stop_li.prettify()}")

        if not stops_data and direction_wrappers: # Avisa se encontrou direções mas nenhuma parada
            print(f"  AVISO: Nenhuma parada individual extraída para a linha {line_number_ref or line_name_ref} em {line_url_ref}, apesar dos wrappers de direção estarem presentes.")
        return stops_data 