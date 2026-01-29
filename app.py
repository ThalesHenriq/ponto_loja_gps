import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import pytz
from PIL import Image
import io
import requests
from geopy.distance import geodesic
from streamlit_js_eval import streamlit_js_eval

# 1. CONFIGURAÇÃO ORBTECH
st.set_page_config(page_title="OrbTech Ponto Pro", page_icon="🛡️", layout="centered")

def abrir_conexao():
    return sqlite3.connect('ponto_loja.db', check_same_thread=False)

def inicializar_banco():
    conn = abrir_conexao()
    cursor = conn.cursor()
    # Tabela de Configurações
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes 
                      (id INTEGER PRIMARY KEY, nome_empresa TEXT, lat REAL, lon REAL, 
                       raio_metros REAL, ip_loja TEXT, modo_trava TEXT)''')
    # Tabela de Funcionários
    cursor.execute('CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
    # Tabela de Registros
    cursor.execute('''CREATE TABLE IF NOT EXISTS registros 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT, tipo TEXT, 
                       data_hora TEXT, data_iso TEXT, foto BLOB)''')
    
    if cursor.execute("SELECT COUNT(*) FROM configuracoes").fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes VALUES (1, 'Empresa Cliente', -23.5505, -46.6333, 50.0, '0.0.0.0', 'GPS')")
    
    conn.commit()
    conn.close()

def get_ip_usuario():
    try: return requests.get('https://api.ipify.org', timeout=5).text
    except: return "Indisponível"

def verificar_batida_hoje(nome, tipo):
    conn = abrir_conexao()
    hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date().isoformat()
    query = "SELECT COUNT(*) FROM registros WHERE funcionario = ? AND tipo = ? AND data_iso = ?"
    resultado = conn.execute(query, (nome, tipo, hoje)).fetchone()[0]
    conn.close()
    return resultado > 0

# --- INICIALIZAÇÃO ---
inicializar_banco()
conn = abrir_conexao()
conf = pd.read_sql_query("SELECT * FROM configuracoes WHERE id=1", conn).iloc[0]
lista_func = pd.read_sql_query("SELECT nome FROM funcionarios ORDER BY nome", conn)['nome'].tolist()
conn.close()

# --- INTERFACE DO FUNCIONÁRIO ---
st.title(f"🏢 {conf['nome_empresa']}")
st.write(f"🔒 Segurança OrbTech: **Modo {conf['modo_trava']} Ativo**")

ip_atual = get_ip_usuario()
loc = None
if conf['modo_trava'] == 'GPS':
    loc = streamlit_js_eval(js_expressions="new Promise((resolve, reject) => { navigator.geolocation.getCurrentPosition(pos => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}), err => reject(err), {enableHighAccuracy: true, timeout: 10000}) })", key="get_location")

usuario = st.selectbox("Selecione seu nome:", [""] + lista_func)

if usuario:
    autorizado = False
    
    # Validação por IP
    if conf['modo_trava'] == 'IP':
        if ip_atual == conf['ip_loja'] or conf['ip_loja'] == '0.0.0.0':
            st.success("✅ Rede Autorizada")
            autorizado = True
        else:
            st.error(f"❌ Fora da Rede da Loja! (Seu IP: {ip_atual})")
            
    # Validação por GPS
    elif conf['modo_trava'] == 'GPS':
        if loc:
            dist = geodesic((conf['lat'], conf['lon']), (loc['lat'], loc['lon'])).meters
            if dist <= conf['raio_metros']:
                st.success(f"✅ Localização confirmada ({int(dist)}m)")
                autorizado = True
            else:
                st.error(f"❌ Fora do Raio! Você está a {int(dist)}m da loja.")
        else:
            st.warning("📡 Buscando sinal de GPS... Verifique as permissões.")

    if autorizado:
        foto = st.camera_input("Foto obrigatória para bater o ponto")
        if foto:
            st.write("---")
            c1, c2 = st.columns(2)
            agora = datetime.now(pytz.timezone('America/Sao_Paulo'))
            
            def salvar_ponto(tipo):
                conn = abrir_conexao()
                img_bin = io.BytesIO(foto.getvalue()).getvalue()
                conn.execute("INSERT INTO registros (funcionario, tipo, data_hora, data_iso, foto) VALUES (?,?,?,?,?)",
                             (usuario, tipo, agora.strftime("%d/%m/%Y %H:%M:%S"), agora.date().isoformat(), img_bin))
                conn.commit()
                conn.close()
                st.success(f"✅ {tipo} registrado!")
                st.balloons()
                st.rerun()

            # Lógica de bloqueio de duplicidade
            if not verificar_batida_hoje(usuario, "Entrada"):
                c1.button("🚀 ENTRADA", on_click=salvar_ponto, args=("Entrada",), use_container_width=True)
            else: c1.info("Entrada OK")

            if not verificar_batida_hoje(usuario, "Saída Final"):
                c2.button("🏠 SAÍDA", on_click=salvar_ponto, args=("Saída Final",), use_container_width=True)
            else: c2.info("Saída OK")

# --- PAINEL ADMINISTRATIVO (SIDEBAR) ---
with st.sidebar:
    st.header("🔐 Admin OrbTech")
    senha = st.text_input("Senha", type="password")
    
    if senha == "1234":
        # 1. Configurações de Trava
        with st.expander("🛠️ Configurações & Trava"):
            n_empresa = st.text_input("Nome da Empresa", value=conf['nome_empresa'])
            modo = st.radio("Modo de Segurança", ["GPS", "IP"], index=0 if conf['modo_trava'] == 'GPS' else 1)
            n_lat = st.number_input("Lat", value=conf['lat'], format="%.6f")
            n_lon = st.number_input("Lon", value=conf['lon'], format="%.6f")
            n_raio = st.number_input("Raio (m)", value=float(conf['raio_metros']))
            
            st.code(f"Seu IP: {ip_atual}")
            n_ip = st.text_input("IP Autorizado", value=conf['ip_loja'])
            if st.button("Usar meu IP atual"): n_ip = ip_atual
            
            if st.button("Salvar Configurações"):
                conn = abrir_conexao()
                conn.execute("UPDATE configuracoes SET nome_empresa=?, lat=?, lon=?, raio_metros=?, ip_loja=?, modo_trava=? WHERE id=1",
                             (n_empresa, n_lat, n_lon, n_raio, n_ip, modo))
                conn.commit()
                conn.close()
                st.rerun()

        # 2. Relatórios
        with st.expander("📊 Relatório Excel"):
            if st.button("Gerar Espelho de Ponto"):
                conn = abrir_conexao()
                df = pd.read_sql_query("SELECT funcionario, tipo, data_iso, data_hora FROM registros", conn)
                conn.close()
                if not df.empty:
                    df['data_hora'] = pd.to_datetime(df['data_hora'], format='%d/%m/%Y %H:%M:%S')
                    esp = df.pivot_table(index=['funcionario', 'data_iso'], columns='tipo', values='data_hora', aggfunc='first').reset_index()
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        esp.to_excel(writer, index=False, sheet_name='Ponto', startrow=4)
                        ws = writer.sheets['Ponto']
                        ws['A1'] = f"EMPRESA: {conf['nome_empresa'].upper()}"
                        ws[f'A{len(esp)+7}'] = "_________________________________\nASSINATURA DO COLABORADOR"
                    
                    st.download_button("⬇️ Baixar Planilha", output.getvalue(), f"ponto_{conf['nome_empresa']}.xlsx")

        # 3. Auditoria Visual
        with st.expander("📸 Ver Fotos"):
            conn = abrir_conexao()
            fotos = pd.read_sql_query("SELECT funcionario, tipo, data_hora, foto FROM registros ORDER BY id DESC LIMIT 5", conn)
            conn.close()
            for _, r in fotos.iterrows():
                st.write(f"**{r['funcionario']}** ({r['tipo']})")
                if r['foto']: st.image(r['foto'], width=150)
