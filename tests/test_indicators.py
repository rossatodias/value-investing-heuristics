import pandas as pd

from value_investing_heuristics.data import normalize_cnpj
from value_investing_heuristics.indicators import add_fundamental_indicators


def test_normalize_cnpj_keeps_14_digits():
    assert normalize_cnpj("33.042.730/0001-04") == "33042730000104"


def test_lucro_oper_proxy_invalid_when_non_positive():
    df = pd.DataFrame(
        {
            "ativoCirc": [10.0, 10.0],
            "passivoCirc": [5.0, 5.0],
            "lucroLiq": [2.0, 2.0],
            "patLiq": [20.0, 20.0],
            "receitaBruta": [40.0, 40.0],
            "dividaLiq": [12.0, 12.0],
            "lucroOper": [6.0, -1.0],
        }
    )
    out = add_fundamental_indicators(df)
    assert out.loc[0, "divida_liquida_lucro_oper_proxy"] == 2.0
    assert pd.isna(out.loc[1, "divida_liquida_lucro_oper_proxy"])
    assert out.loc[0, "lucro_oper_proxy_valido"]
    assert not out.loc[1, "lucro_oper_proxy_valido"]
