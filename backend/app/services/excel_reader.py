"""
Lecture intelligente des fichiers Excel.

Gère deux problèmes courants :
1. Lignes de titre / préambule AVANT la vraie ligne d'en-tête (colonnes "Unnamed").
2. Fichiers `.xls` qui sont en réalité du HTML ou du XML SpreadsheetML déguisé
   (exports Jira, Mantis, outils internes…). `xlrd` échoue sur ces fichiers.

La détection du format se fait sur la signature binaire, pas sur l'extension.
"""
from io import BytesIO
from pathlib import Path
from typing import Union

import pandas as pd


def detect_header_row(raw: pd.DataFrame, max_scan: int = 30) -> int:
    """Index de la ligne d'en-tête réelle.

    Une ligne d'en-tête est : (1) bien remplie ET (2) composée de valeurs
    majoritairement DISTINCTES. Cela permet d'ignorer :
      - les lignes vides ou quasi vides (titres sur 1 cellule),
      - les lignes de titre fusionnées (même valeur répétée sur toute la largeur,
        ex. "OGA DIR" × 10 dans les exports Jira).
    """
    scan = raw.head(max_scan)
    if scan.empty:
        return 0
    ncols = scan.shape[1]
    min_filled = max(2, int(ncols * 0.5))
    min_unique = max(2, int(ncols * 0.6))

    for pos in range(len(scan)):
        row = scan.iloc[pos]
        if int(row.notna().sum()) < min_filled:
            continue
        unique = row.dropna().astype(str).str.strip().nunique()
        if unique >= min_unique:
            return pos

    # Repli : la ligne la plus remplie
    counts = scan.notna().sum(axis=1)
    return int(counts.values.argmax()) if int(counts.max()) > 0 else 0


def _apply_detected_header(raw: pd.DataFrame) -> pd.DataFrame:
    """Transforme un DataFrame brut (header=None) en DataFrame avec le bon en-tête."""
    hr = detect_header_row(raw)
    header = [str(c).strip() for c in raw.iloc[hr].tolist()]
    df = raw.iloc[hr + 1:].copy()
    df.columns = header
    return df.reset_index(drop=True)


def _read_html_disguised(content: bytes) -> pd.DataFrame:
    """Lit un .xls qui est en fait du HTML/XML (table déguisée).

    Les exports type Jira mettent l'en-tête dans des balises <th> et découpent le
    tableau en plusieurs blocs (titre / données / pied). On lit donc avec
    détection d'en-tête automatique (<th>) et on garde la table contenant le plus
    de lignes (= les données). Si aucune <th> n'est présente, on retombe sur la
    détection manuelle de la ligne d'en-tête.
    """
    tables = pd.read_html(BytesIO(content))  # header auto (lit les <th>)
    if not tables:
        raise ValueError("Aucun tableau trouvé dans le fichier.")

    best = max(tables, key=lambda t: t.shape[0])

    # Colonnes entières = aucune <th> détectée → détection manuelle
    if all(isinstance(c, int) for c in best.columns):
        raw_tables = pd.read_html(BytesIO(content), header=None)
        raw = max(raw_tables, key=lambda t: t.shape[0] * t.shape[1])
        return _apply_detected_header(raw)

    # Aplatir d'éventuels en-têtes multi-niveaux et nettoyer
    best = best.copy()
    best.columns = [
        " ".join(str(x).strip() for x in c) if isinstance(c, tuple) else str(c).strip()
        for c in best.columns
    ]
    return best.reset_index(drop=True)


def _read_binary(content: bytes, filename: str) -> pd.DataFrame:
    """Lit un vrai fichier Excel binaire (.xlsx zip ou .xls OLE2)."""
    if content[:4] == b"PK\x03\x04":           # ZIP → xlsx
        engine = "openpyxl"
    elif content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # OLE2 → xls
        engine = "xlrd"
    else:
        engine = "openpyxl" if filename.lower().endswith("xlsx") else "xlrd"
    raw = pd.read_excel(BytesIO(content), header=None, engine=engine, nrows=30)
    hr = detect_header_row(raw)
    return pd.read_excel(BytesIO(content), header=hr, engine=engine)


def _read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    """Détecte le format réel et lit le fichier en conséquence."""
    sniff = content[:4096].lower().lstrip(b"\xef\xbb\xbf \t\r\n")
    is_html = sniff.startswith(b"<") and (b"<table" in sniff or b"<html" in sniff or b"<?xml" in sniff)
    if is_html:
        return _read_html_disguised(content)
    return _read_binary(content, filename)


def read_excel_bytes(content: bytes, filename: str, nrows: int = None) -> pd.DataFrame:
    """Lit un Excel depuis des octets (détection format + saut du préambule)."""
    df = _read_dataframe(content, filename)
    return df.head(nrows) if nrows is not None else df


def read_excel_path(path: Union[str, Path], nrows: int = None) -> pd.DataFrame:
    """Lit un Excel depuis un chemin (détection format + saut du préambule)."""
    p = Path(path)
    content = p.read_bytes()
    df = _read_dataframe(content, p.name)
    return df.head(nrows) if nrows is not None else df
