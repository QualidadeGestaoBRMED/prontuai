#!/usr/bin/env python3
"""
Aplica as decisões dos 21 conflitos da importação do CSV.

Uso:
  PRONTUAI_API=http://127.0.0.1:8010 python3 scripts/resolver_conflitos_importacao.py

As decisões e o critério de cada uma estão embutidos abaixo. Foram tomadas com
base na contagem real de pedidos do BRNET
(SELECT count(*) FROM documents, unnest(exams_brnet)) mais convenção médica.

Idempotente: conflito já resolvido é ignorado (a API responde 409 "Conflito já
resolvido" e o script segue).
"""
import json, urllib.request, urllib.parse

import os
B = os.getenv("PRONTUAI_API", "http://127.0.0.1:8010").rstrip("/") + "/v1/exams"

def get(url):
    with urllib.request.urlopen(url) as r: return json.load(r)
def post(url, corpo):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(),
                                headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)
def delete(url):
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req) as r: return r.status
    except urllib.error.HTTPError as e: return e.code

pais = {p["name"]: p["id"] for p in get(f"{B}?limit=500")["items"]}
conflitos = {c["name"]: c["id"] for c in get(f"{B}/conflicts")}

# ---- DESCARTAR: nao sao nome de exame, ou sao exames distintos ----
DESCARTAR = {
 "ap/perfil":            "sufixo de projecao radiografica, nao nome de exame",
 "pa/obliqua":           "sufixo de projecao radiografica, nao nome de exame",
 "efp, pfp, espiro":     "lista de siglas colada numa celula do CSV",
 "glicemia de jejum":    "glicemia de jejum e glicose sao exames DISTINTOS (BRNET pede os dois: 1603 e 330)",
 "glicose":              "idem, sentido inverso",
}
# ---- ATRIBUIR: um candidato so, por dado do BRNET ou convencao medica ----
ATRIBUIR = {
 "chumbo no sangue total":               ("chumbo sanguineo", "sangue total = sangue, nao soro; BRNET pede sanguineo 12x vs serico 2x"),
 "pbb (blood lead)":                     ("chumbo sanguineo", "blood lead = chumbo em sangue total"),
 "plumbemia":                            ("chumbo sanguineo", "plumbemia = chumbo no sangue"),
 "prova de funcao pulmonar basica":      ("espirometria", "sinonimo classico; o outro candidato e 'espirometria (nao usar)', 0 pedidos"),
 "exame de campo visual":                ("campimetria", "BRNET pede campimetria 50x, campimetria visual 0x"),
 "rx coluna cervical":                   ("radiografia de coluna cervical ap", "unico candidato que o BRNET pede (4x)"),
 "tiroxina livre":                       ("t4 livre", "tiroxina = T4; 't 4 livre' e variante de OCR, 0 pedidos"),
 "atl (audiometria tonal limiar)":       ("audiometria tonal", "ATL = audiometria tonal limiar; BRNET pede tonal 2436x vs tonal e vocal 4x"),
 "glicemia basal":                       ("glicemia de jejum", "basal = em jejum"),
 "glicose em jejum":                     ("glicemia de jejum", "explicitamente em jejum"),
 "papanicolaou":                         ("colpocitologia", "sinonimos do mesmo exame; ambos os pais em quarentena, sem efeito no match"),
 "preventivo":                           ("colpocitologia", "idem"),
 "citologia oncotica cervicovaginal":    ("colpocitologia", "idem"),
 "exame citopatologico do colo uterino": ("colpocitologia", "idem"),
}
# ---- FUNDIR: o termo ja e pai em quarentena com 0 variacoes; apaga e vira variacao ----
FUNDIR = {
 "avaliacao psicologia":           ("avaliacao psicologica", "variante tipografica; pai ativo pedido 848x"),
 "radiografia de coluna cervical": ("radiografia de coluna cervical ap", "variante sem o AP; pai ativo pedido 4x"),
}

ok=err=ja=0
print("=== DESCARTADOS ===")
for nome, motivo in DESCARTAR.items():
    cid = conflitos.get(nome)
    if not cid:
        print(f"  [ja] '{nome}' — conflito ja resolvido"); ja+=1; continue
    st,_ = post(f"{B}/conflicts/{cid}/resolve", {"resolution":"descartada"})
    print(f"  [{st}] '{nome}' — {motivo}"); ok+= st==200; err+= st!=200

print("\n=== FUNDIDOS (pai em quarentena apagado) ===")
for nome, (destino, motivo) in FUNDIR.items():
    cid = conflitos.get(nome)
    if not cid:
        print(f"  [ja] '{nome}' — conflito ja resolvido"); ja+=1; continue
    pid_velho = pais.get(nome)
    if pid_velho:
        c = delete(f"{B}/{pid_velho}")
        print(f"  pai '{nome}' apagado (HTTP {c})")
    st, resp = post(f"{B}/conflicts/{cid}/resolve",
                    {"resolution":"atribuida","parent_id":pais.get(destino)})
    print(f"  [{st}] '{nome}' -> '{destino}' — {motivo}")
    if st!=200: print(f"        {resp.get('detail')}")
    ok+= st==200; err+= st!=200

print("\n=== ATRIBUIDOS ===")
for nome, (destino, motivo) in ATRIBUIR.items():
    cid = conflitos.get(nome); pid = pais.get(destino)
    if not cid:
        print(f"  [ja] '{nome}' — conflito ja resolvido"); ja+=1; continue
    if not pid:
        print(f"  ERRO '{nome}': pai '{destino}' nao existe no catalogo"); err+=1; continue
    st, resp = post(f"{B}/conflicts/{cid}/resolve", {"resolution":"atribuida","parent_id":pid})
    print(f"  [{st}] '{nome}' -> '{destino}'")
    print(f"        {motivo}")
    if st!=200: print(f"        ERRO: {resp.get('detail')}")
    ok+= st==200; err+= st!=200

print(f"\nresolvidos agora: {ok}  |  ja resolvidos: {ja}  |  falhas: {err}")
print("restam abertos:", len(get(f'{B}/conflicts')))
