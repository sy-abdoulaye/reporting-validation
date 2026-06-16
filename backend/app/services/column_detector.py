from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from app.services.excel_reader import read_excel_path


class ColumnDetector:
    """ service pour détecter les colonnes présentes dans les données d'entrée"""
    def __init__(self):
        self.date_patterns = [
            r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
        ]

    def analyse_file(self, file_path: Path) -> Dict[str, Any]:

        df = read_excel_path(file_path)
        df.columns = [self.cleanup_column_name(col) for col in df.columns]

        columns = []
        for col_name in df.columns:
            col_data = df[col_name]
            analysis = self.analyze_column(col_data, col_name)
            columns.append(analysis)

        return {
            "total_rows": int(len(df)),
            "total_columns": int(len(columns)),
            "columns": columns,
            "preview": self.sanitize_preview(df.head(5).fillna('').to_dict('records'))
        }

    def sanitize_preview(self, preview_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def sanitize_value(value: Any) -> Any:
            if isinstance(value, (np.integer, np.int64, np.int32)):
                return int(value)
            if isinstance(value, (np.floating, np.float64, np.float32)):
                return float(value)
            if isinstance(value, (np.bool_, bool)):
                return bool(value)
            if isinstance(value, (pd.Timestamp, pd.Timedelta)):
                return str(value)
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            if isinstance(value, bytes):
                return value.decode('utf-8', errors='ignore')
            return value

        return [
            {key: sanitize_value(val) for key, val in row.items()}
            for row in preview_rows
        ]

    def cleanup_column_name(self, col_name: str) -> str:
        """Nettoie le nom de la colonne en supprimant les espaces et en gérant les valeurs manquantes"""
        if pd.isna(col_name):
            return "unknown"
        return col_name.strip()

    def analyze_column(self, series: pd.Series, col_name: str) -> Dict[str, Any]:

        # Nettoyer les données en supprimant les valeurs manquantes pour une analyse plus précise
        cleaned = series.dropna()
        # Détecter les types de données présents dans la colonne
        type = self.detect_type(cleaned)
        samples = cleaned.head(5).tolist()  if len(cleaned) > 0 else [] # Échantillons pour validation

        # Calculer les statistiques de base pour la colonne
        stats = {
            "total": int(len(series)), # Nombre total de valeurs dans la colonne
            "null_count": int(series.isna().sum()), # Nombre de valeurs manquantes
            "unique_count": int(series.nunique()), # Nombre de valeurs uniques
            "null_percentage": float(round(series.isna().sum() / len(series) * 100, 2)) # Pourcentage de valeurs manquantes
        }

        suggested_width = self.suggest_width(col_name, samples, type)

        return {
            "name": col_name,
            "type": type,
            "stats": stats,
            "samples": [str(s)[:50] for s in samples],
            "suggested_width": suggested_width,
            "is_date": self.is_date_column(cleaned), # Indique si la colonne est probablement une date
            "is_numeric": self.is_numeric_column(cleaned) # Indique si la colonne est probablement numérique
        }

    def detect_type(self, series: pd.Series) -> str:
        """Détecte le type de données d'une série en se basant sur les types de données et les échantillons"""
        if series.empty:
            return "unknown"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "date"
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if pd.api.types.is_string_dtype(series):
            return "string"
        return "unknown"

    def suggest_width(self, col_name: str, samples: list, type: str) -> int:
        """Suggère une largeur de colonne pour l'affichage en fonction du type et des échantillons"""
        base_width = max(len(col_name), 10) # Largeur de base basée sur le nom de la colonne
        if type == "date":
            return max(base_width, 20) # Les dates peuvent être plus longues
        if type == "numeric":
            return max(base_width, 15) # Les nombres peuvent être plus longs
        if samples:
            max_sample_length = max(len(str(s)) for s in samples)
            return max(base_width, min(max_sample_length + 5, 50)) # Ajouter une marge aux échantillons
        return base_width

    def is_date_column(self, series: pd.Series) -> bool:
        """Détecte si une colonne est probablement une date en se basant sur les types de données et les échantillons"""
        if series.empty:
            return False
        if pd.api.types.is_datetime64_any_dtype(series):
            return True
        # Vérifier les échantillons pour détecter les formats de date courants
        for sample in series.head(10):  # Vérifier les 10 premiers échantillons
            if isinstance(sample, str):
                for pattern in self.date_patterns:
                    if pd.Series([sample]).str.match(pattern).any():
                        return True
        return False

    def is_numeric_column(self, series: pd.Series) -> bool:
        """Détecte si une colonne est probablement numérique en se basant sur les types de données et les échantillons"""
        if series.empty:
            return False
        if pd.api.types.is_numeric_dtype(series):
            return True
        # Vérifier les échantillons pour détecter les formats numériques courants
        for sample in series.head(10):  # Vérifier les 10 premiers échantillons
            if isinstance(sample, (int, float)):
                return True
            if isinstance(sample, str):
                try:
                    float(sample.replace(",", "."))  # Gérer les nombres avec des virgules
                    return True
                except ValueError:
                    continue
        return False