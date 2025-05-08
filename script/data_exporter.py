import pandas as pd
from typing import List, Dict, Any, Union

class DataExporter:
    """
    Classe responsável por exportar dados para diferentes formatos.
    Atualmente, suporta a exportação para CSV.
    """

    def __init__(self):
        """Inicializa o DataExporter."""
        pass # Nenhuma inicialização específica necessária por enquanto

    def export_to_csv(self, data: Union[List[Dict[Any, Any]], pd.DataFrame], filename: str, expected_columns: list[str]):
        """
        Cria um DataFrame do Pandas com os dados fornecidos (se não for já um DataFrame),
        garante que todas as colunas esperadas existam, reordena as colunas e salva
        em um arquivo CSV.

        Args:
            data: Uma lista de dicionários ou um DataFrame do Pandas contendo os dados.
            filename: O nome do arquivo CSV de saída.
            expected_columns: Uma lista de strings com os nomes das colunas na ordem desejada.
        """
        if isinstance(data, list):
            if not data:
                print("\nNenhum dado fornecido para exportação (lista vazia). O arquivo CSV não será criado.")
                return
            print(f"\nConvertendo lista de {len(data)} registros para DataFrame...")
            df = pd.DataFrame(data)
        elif isinstance(data, pd.DataFrame):
            if data.empty:
                print("\nDataFrame fornecido está vazio. O arquivo CSV não será criado.")
                return
            print(f"\nProcessando DataFrame fornecido com {len(data)} registros...")
            df = data # df já é um DataFrame
        else:
            print("\nFormato de dados inválido para exportação. Esperado: lista de dicionários ou DataFrame Pandas.")
            return

        # Garantir que todas as colunas esperadas existam, adicionando-as vazias se necessário
        for col in expected_columns:
            if col not in df.columns:
                print(f"  Adicionando coluna faltante: {col}")
                df[col] = pd.NA # Usar pd.NA para dados ausentes é mais consistente

        # Reordenar colunas do DataFrame
        try:
            df = df[expected_columns]
        except KeyError as e:
            # Isso pode acontecer se uma coluna em expected_columns não foi criada acima
            # (o que não deveria acontecer com a lógica atual, mas é um bom failsafe)
            print(f"Erro ao reordenar colunas. Uma ou mais colunas esperadas não existem no DataFrame: {e}")
            print(f"Colunas esperadas: {expected_columns}")
            print(f"Colunas existentes no DataFrame: {list(df.columns)}")
            print("Prosseguindo com as colunas existentes que correspondem às esperadas.")
            # Filtra expected_columns para incluir apenas aquelas que realmente existem no df
            valid_columns_for_ordering = [col for col in expected_columns if col in df.columns]
            df = df[valid_columns_for_ordering]

        print("\nPré-visualização do DataFrame final:")
        print(df.head().to_string())
        print("\nInformações do DataFrame:")
        df.info()

        try:
            df.to_csv(filename, index=False, encoding='utf-8')
            print(f"\nDataFrame salvo com sucesso em {filename}")
        except Exception as e:
            print(f"\nErro ao salvar DataFrame para CSV '{filename}': {e}") 