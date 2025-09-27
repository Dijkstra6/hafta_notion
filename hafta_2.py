import requests
import os

from dotenv import load_dotenv

load_dotenv()  # .env dosyasını yükler

NOTION_TOKEN = os.getenv("API_TOKEN")  # API key'in
DATABASE_ID = "27bf37d4-26e2-800d-8971-fb050bc7ed9c"  # Formülün olduğu database ID
BLOCK_ID = "27bf37d4-26e2-8082-8359-e740c0964af1"     # Güncellenecek text bloğunun ID'si
FORMULA_PROPERTY = "Formula"  # Formül kolonunun adı
FILTER_TITLE_PROP = ""                              # genelde başlık sütunu "Name"
FILTER_TITLE_VALUE = None                               # ör: "Bu Hafta" (yoksa None bırak)
#print("Token:", api_token)
# Notion API ortak başlıklar
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# --------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------
def coerce_formula_to_str(formula_obj: dict) -> str:
    """Formula objesini stringe çevirir (string/number/boolean/date destekli)."""
    if formula_obj.get("string") is not None:
        return formula_obj["string"]
    if formula_obj.get("number") is not None:
        return str(formula_obj["number"])
    if formula_obj.get("boolean") is not None:
        return "true" if formula_obj["boolean"] else "false"
    if formula_obj.get("date") and formula_obj["date"].get("start"):
        return formula_obj["date"]["start"]
    return ""  # null -> boş

def query_props():
    """Databaseden satırları çeker; hata varsa gövdeyi yazdırır."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    body = {"page_size": 10}
    if FILTER_TITLE_VALUE:
        body["filter"] = {"property": FILTER_TITLE_PROP, "title": {"equals": FILTER_TITLE_VALUE}}

    r = requests.post(url, headers=headers, json=body)
    print("QUERY:", r.status_code)
    if r.status_code != 200:
        print(r.text)
        r.raise_for_status()

    results = r.json().get("results", [])
    # Her satırın properties + __id alanını toplayalım
    return [row["properties"] | {"__id": row["id"]} for row in results]

def print_probe(rows):
    """Teşhis amaçlı: gelen satırların propertylerini ve Formula değerlerini gösterir."""
    print("— PROBE —")
    for i, props in enumerate(rows, 1):
        keys = list(props.keys())
        keys.remove("__id")
        val = None
        if FORMULA_PROPERTY in props and props[FORMULA_PROPERTY]["type"] == "formula":
            val = coerce_formula_to_str(props[FORMULA_PROPERTY]["formula"])
        print(f"[{i}] id={props['__id']}  props={keys}")
        print(f"    {FORMULA_PROPERTY} -> {val!r}")
    print("— END —")

def get_target_value(rows) -> str:
    """İlk dolu Formula değerini döndür; hiçbiri dolu değilse '—'."""
    for p in rows:
        if FORMULA_PROPERTY in p and p[FORMULA_PROPERTY]["type"] == "formula":
            v = coerce_formula_to_str(p[FORMULA_PROPERTY]["formula"])
            if v not in (None, ""):
                return v
    return "—"

# --------------------------------------------------------------------
# CALLOUT odaklı okuma/yazma
# --------------------------------------------------------------------
def get_callout_text(block_id: str) -> str:
    """Callout bloğunun mevcut metnini döndürür; tip callout değilse hata verir."""
    r = requests.get(f"https://api.notion.com/v1/blocks/{block_id}", headers=headers)
    if r.status_code != 200:
        print(r.text)
    r.raise_for_status()
    data = r.json()

    if data["type"] != "callout":
        raise RuntimeError(f"Hedef blok 'callout' değil (type={data['type']}). Lütfen CALL OUT blok ID'si verin.")

    rt = data["callout"].get("rich_text", []) or []
    return "".join([t.get("text", {}).get("content", "") for t in rt])

def patch_callout_text(block_id: str, new_text: str, bold: bool = True, color: str = "green"):
    """Callout rich_text içeriğini (stil dahil) günceller."""
    payload = {
        "callout": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": new_text},
                    "annotations": {
                        "bold": bold,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": color
                    }
                }
            ]
        }
    }
    r = requests.patch(f"https://api.notion.com/v1/blocks/{block_id}", headers=headers, json=payload)
    if r.status_code != 200:
        print(r.text)
    r.raise_for_status()



# --------------------------------------------------------------------
# Keşif: sayfa çocuk bloklarını listele (callout id bulma kolaylığı)
# --------------------------------------------------------------------
def list_page_blocks(page_id: str):
    """
    Bir sayfanın (PAGE_ID) içindeki blokları listeler.
    Çıktıda: block_type | block_id | metin
    """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(r.text)
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    for b in results:
        block_id = b["id"]
        block_type = b["type"]
        text = ""
        inner = b.get(block_type, {})
        if isinstance(inner, dict) and "rich_text" in inner and inner["rich_text"]:
            text = "".join([t["text"]["content"] for t in inner["rich_text"]])
        print(f"{block_type:12s} | {block_id} | {text}")
    return results

# --------------------------------------------------------------------
# Ana akış
# --------------------------------------------------------------------
if __name__ == "__main__":
    rows = query_props()
    print_probe(rows)
    value = get_target_value(rows)  # ör: "2"

    # Callout metnini formatla: "{Hafta}. Hafta"
    formatted = f"{value}. Hafta"

    # Karşılaştırma yapmadan direkt patch et (stil de burada uygulanıyor)
    patch_callout_text(BLOCK_ID, formatted, bold=True, color="green")
    print(f"Güncellendi ✅  (value={value!r})  --> '{formatted}' (yeşil & bold)")
