import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import pytz
from PIL import Image
import io
from geopy.distance import geodesic
from streamlit_js_eval import streamlit_js_eval

# 1. CONFIGURAÇÃO DA ORBTECH
st.set_page_config(page_title="OrbTech GeoPonto 2026", page_icon="📍")

def abrir_conexao():
    return sqlite3.connect('ponto_loja.db', check_same_thread=False)

def inicializar_banco():
    conn = abrir_conexao()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes 
                      (id INTEGER PRIMARY KEY, lat REAL, lon REAL, raio_metros REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS registros 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT, tipo TEXT, data_hora TEXT, foto BLOB)''')
    
    cursor.execute("SELECT COUNT(*) FROM configuracoes")
    if cursor.fetchone()[0] == 0:
        # Padrão: Centro de SP (O gerente deve mudar no painel)
        cursor.execute("INSERT INTO configuracoes VALUES (1, -23.5505, -46.6333, 50.0)")
    
    # Migração para garantir que novas colunas existam
    try: cursor.execute("ALTER TABLE registros ADD COLUMN data_iso TEXT")
    except: pass
    
    conn.commit()
    conn.close()

def registrar_ponto_completo(nome, tipo, foto_capturada):
    try:
        conn = abrir_conexao()
        cursor = conn.cursor()
        fuso_br = pytz.timezone('America/Sao_Paulo')
        agora_br = datetime.now(fuso_br)
        data_txt = agora_br.strftime("%d/%m/%Y %H:%M:%S")
        data_iso = agora_br.date().isoformat()
        
        img = Image.open(foto_capturada)
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        
        cursor.execute("INSERT INTO registros (funcionario, tipo, data_hora, data_iso, foto) VALUES (?, ?, ?, ?, ?)", 
                       (nome, tipo, data_txt, data_iso, buf.getvalue()))
        conn.commit()
        conn.close()
        st.success(f"✅ {tipo} registrado com sucesso!")
    except Exception as e:
        st.error(f"Erro: {e}")

# --- INICIALIZAÇÃO ---
inicializar_banco()
conn = abrir_conexao()
loja_config = pd.read_sql_query("SELECT lat, lon, raio_metros FROM configuracoes WHERE id=1", conn).iloc[0]
lista_func = pd.read_sql_query("SELECT nome FROM funcionarios", conn)['nome'].tolist()
conn.close()

st.title("📍 OrbTech GeoPonto")
st.write("Validação por Localização e Foto")

# --- CAPTURA DE GPS AUTOMÁTICA ---
loc = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: pos.coords.latitude, lon: pos.coords.longitude}}, '*') }, err => { console.log(err) })", key="get_location")

usuario = st.selectbox("Selecione seu nome:", [""] + lista_func)

if usuario:
    if loc:
        user_lat = loc['lat']
        user_lon = loc['lon']
        
        # Cálculo da distância
        distancia = geodesic((loja_config['lat'], loja_config['lon']), (user_lat, user_lon)).meters
        
        if distancia <= loja_config['raio_metros']:
            st.success(f"📍 Localização confirmada! ({int(distancia)}m da loja)")
            foto = st.camera_input("Capture sua foto para validar")
            
            if foto:
                c1, c2 = st.columns(2)
                if c1.button("🚀 ENTRADA", use_container_width=True): registrar_ponto_completo(usuario, "Entrada", foto)
                if c2.button("🏠 SAÍDA", use_container_width=True): registrar_ponto_completo(usuario, "Saída Final", foto)
        else:
            st.error(f"❌ Fora do raio permitido! Você está a {int(distancia)}m da loja. O limite é {int(loja_config['raio_metros'])}m.")
            st.warning("Aproxime-se do estabelecimento para bater o ponto.")
    else:
        st.info("Aguardando sinal do GPS... Certifique-se de que a localização do celular está ativa.")

# --- PAINEL DO GERENTE ---
with st.sidebar:
    st.header("⚙️ Admin OrbTech")
    if st.text_input("Senha", type="password") == "1234":
        st.subheader("Configurar Local da Loja")
        st.caption("Pegue as coordenadas no Google Maps")
        n_lat = st.number_input("Latitude", value=loja_config['lat'], format="%.6f")
        n_lon = st.number_input("Longitude", value=loja_config['lon'], format="%.6f")
        n_raio = st.number_input("Raio (metros)", value=float(loja_config['raio_metros']))
        
        if st.button("Salvar Localização"):
            conn = abrir_conexao()
            conn.execute("UPDATE configuracoes SET lat=?, lon=?, raio_metros=? WHERE id=1", (n_lat, n_lon, n_raio))
            conn.commit()
            conn.close()
            st.success("Localização atualizada!")
            st.rerun()
