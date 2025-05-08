import os
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time  # Para delays, se necessário com Google
from typing import Optional, Tuple, List
from dotenv import load_dotenv
load_dotenv()

import requests


class GeoCoder:
    """
    Classe para geocodificação usando Nominatim e/ou Google Geocoding API.
    service_preference: 'nominatim', 'google' ou 'both' (tenta Nominatim e, em caso de falha, Google)
    """

    def __init__(
        self,
        user_agent_suffix: str = "DefaultMaricaScraper/1.0",
    ):
        # --- Configuração Nominatim ---
        self.nominatim_user_agent = f"geopy-Nominatim-client/{user_agent_suffix}"
        self.geolocator_nominatim = Nominatim(user_agent=self.nominatim_user_agent)
        # Respeita 1.1s entre requisições
        self.geocode_nominatim_service = RateLimiter(
            self.geolocator_nominatim.geocode, min_delay_seconds=1.1
        )

        # --- Configuração Google Maps ---
        self.google_api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
        if self.google_api_key:
            print("GeoCoder: Chave da API do Google Maps encontrada.")
        else:
            print("GeoCoder: Chave da API do Google Maps não encontrada no arquivo .env.")
            print("Dica: Adicione GOOGLE_MAPS_API_KEY=sua_chave_aqui no arquivo .env")

        # --- Constantes de contexto ---
        self.CITY = "Maricá"
        self.STATE = "Rio de Janeiro"
        self.COUNTRY = "Brasil"
        self.COUNTRY_CODE = "BR"  # Para componentes Google

    def _clean_address(self, address: str) -> str:
        """Pode expandir limpezas específicas se necessário."""
        addr = address.replace("Lot ", "Loteamento ")
        if "Ponto Final - " in addr and len(addr.split(" - ")[1]) > 5:
            addr = addr.split(" - ")[1]
        return addr.strip()

    def _geocode_with_nominatim(
        self, address: str
    ) -> Tuple[Optional[float], Optional[float], Optional[str], str]:
        """Tenta Nominatim puro."""
        full = f"{address}, {self.CITY}, {self.STATE}, {self.COUNTRY}"
        try:
            loc = self.geocode_nominatim_service(
                full, addressdetails=True, timeout=10
            )
            if not loc:
                return None, None, None, "nominatim_failed"

            # Confirma cidade
            comp = loc.raw.get("address", {})
            city_found = comp.get("city") or comp.get("town") or comp.get("village")
            if city_found and self.CITY.lower() in city_found.lower():
                return loc.latitude, loc.longitude, loc.address, "nominatim"
            else:
                return (
                    None,
                    None,
                    f"Fora de {self.CITY}: '{loc.address}'",
                    "nominatim_failed",
                )

        except Exception as e:
            return None, None, f"Erro Nominatim ({e})", "nominatim_failed"

    def _geocode_with_google(
        self, address: str, place_id: Optional[str] = None
    ) -> Tuple[Optional[float], Optional[float], Optional[str], str]:
        """
        Geocoding via HTTP. Se 'place_id' for fornecido, ignora o 'address'.
        Retorna (lat, lng, formatted_address, fonte).
        """
        key = os.environ.get('GOOGLE_MAPS_API_KEY')
        if not key:
            return None, None, "API Google não configurada", "google_skipped"

        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"key": key}
        
        # Adiciona componentes para refinar a busca do Google
        components_list = []
        if self.COUNTRY_CODE:
            components_list.append(f"country:{self.COUNTRY_CODE}")
        if self.STATE: # Supondo que STATE seja o nome completo ou sigla correta para 'administrative_area'
            components_list.append(f"administrative_area:{self.STATE}")
        if self.CITY: # Supondo que CITY seja o nome correto para 'locality'
            components_list.append(f"locality:{self.CITY}")
        
        if components_list:
            params["components"] = "|".join(components_list)

        if place_id:
            params["place_id"] = place_id
        else:
            params["address"] = address

        try:
            resp = requests.get(url, params=params)
            resp.raise_for_status()  # Levanta em erro HTTP 4xx/5xx
            data = resp.json()
            status = data.get("status")
            if status != "OK":
                msg = data.get("error_message", status)
                return None, None, f"Google API error: {msg}", "google_failed"

            first = data["results"][0]
            loc = first["geometry"]["location"]
            return loc["lat"], loc["lng"], first.get("formatted_address"), "google"

        except requests.RequestException as e:
            return None, None, f"HTTP error: {e}", "google_failed"
        except (KeyError, IndexError) as e:
            return None, None, f"Parse error: {e}", "google_failed"

    def geocode(
        self, address: str, service: str = "google"
    ) -> Tuple[Optional[float], Optional[float], Optional[str], str]:
        """
        Geocodifica um único endereço.
        service: 'nominatim', 'google' ou 'both'.
        Retorna (lat, lon, endereço_formatado, fonte).
        """
        service = service.lower()
        if service == "nominatim":
            return self._geocode_with_nominatim(address)
        elif service == "google":
            return self._geocode_with_google(address)
        elif service == "both":
            lat, lon, fmt, src = self._geocode_with_nominatim(address)
            if lat is not None:
                return lat, lon, fmt, src
            # fallback
            return self._geocode_with_google(address)
        else:
            raise ValueError("service deve ser 'nominatim', 'google' ou 'both'")

    def add_coordinates_to_dataframe(
        self,
        df: pd.DataFrame,
        stop_name_column: str,
        service: str = "both",  # Mantido o padrão, mas pode ser 'google' para focar
    ) -> pd.DataFrame:
        """
        Para cada linha do df, geocodifica df[stop_name_column] usando o serviço definido.
        Adiciona colunas: latitude, longitude, endereco_geocodificado, geocoding_source.
        Otimizado para geocodificar apenas endereços únicos.
        """
        if stop_name_column not in df.columns:
            print(f"ERRO: A coluna de nome de parada '{stop_name_column}' não existe no DataFrame.")
            # Retorna o DataFrame original ou lança um erro, dependendo da preferência.
            # Por enquanto, apenas adiciona colunas vazias para manter a consistência do tipo de retorno.
            df["latitude"] = None
            df["longitude"] = None
            df["endereco_geocodificado"] = None
            df["geocoding_source"] = "error_column_not_found"
            return df

        unique_stop_names = df[stop_name_column].astype(str).unique()
        num_unique_stops = len(unique_stop_names)
        print(f"Iniciando geocodificação para {num_unique_stops} endereços únicos (de {len(df)} paradas totais). Serviço={service}")

        geocoded_cache = {}
        success_nominatim = 0
        success_google = 0
        failures = 0

        for i, name in enumerate(unique_stop_names):
            print(f"  Geocodificando único [{i + 1}/{num_unique_stops}]: '{name}'")
            lat, lon, fmt, src = self.geocode(name, service=service)
            geocoded_cache[name] = {
                "latitude": lat,
                "longitude": lon,
                "endereco_geocodificado": fmt,
                "geocoding_source": src,
            }
            resultado = "SUCESSO" if lat is not None else "FALHA"
            print(f"    -> {resultado} (fonte: {src})")
            
            if lat is not None:
                if src == "nominatim":
                    success_nominatim += 1
                elif src == "google":
                    success_google += 1
            else:
                failures += 1

            # Pausa entre chamadas, especialmente se o fallback para Google for frequente
            if service in ("google", "both") and src.startswith("google"):
                time.sleep(0.05) # Pequena pausa, pode ser ajustada
            elif service == "nominatim": # Respeita o rate limit do Nominatim já incluso no RateLimiter
                pass # O RateLimiter já cuida disso

        # Mapeia os resultados de volta para o DataFrame original
        df_copy = df.copy()
        df_copy["latitude"] = df_copy[stop_name_column].astype(str).map(lambda x: geocoded_cache.get(x, {}).get("latitude"))
        df_copy["longitude"] = df_copy[stop_name_column].astype(str).map(lambda x: geocoded_cache.get(x, {}).get("longitude"))
        df_copy["endereco_geocodificado"] = df_copy[stop_name_column].astype(str).map(lambda x: geocoded_cache.get(x, {}).get("endereco_geocodificado"))
        df_copy["geocoding_source"] = df_copy[stop_name_column].astype(str).map(lambda x: geocoded_cache.get(x, {}).get("geocoding_source"))

        print("\nResumo da Geocodificação (Endereços Únicos):")
        print(f"  Total Únicos: {num_unique_stops}")
        print(f"  Sucesso Nominatim: {success_nominatim}")
        print(f"  Sucesso Google: {success_google}")
        print(f"  Falhas: {failures}")

        return df_copy
