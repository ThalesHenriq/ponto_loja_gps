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

# 1. CONFIGURAÇÃO DA MARCA ORBTECH
st.set_page_config(page_title="OrbTech Ponto Pro 2026", page_icon="📍", layout="centered")

def abrir_conexao():
    return sqlite3.connect('ponto_loja.db', check_same_thread=False)

def inicializar_banco():
    conn = abrir_conexao()
    cursor = conn.cursor()
    # Tabela de Configurações (Empresa, GPS e IP)
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes 
                      (id INTEGER PRIMARY KEY, nome_empresa TEXT, lat REAL, lon REAL, raio_metros REAL, ip_loja TEXT)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS registros 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT, tipo TEXT, 
                       data_hora TEXT, data_iso TEXT, foto BLOB)''')
    
    # Migrações e Dados Iniciais
    cursor.execute("SELECT COUNT(*) FROM configuracoes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes VALUES (1, 'OrbTech Cliente', -23.5505, -46.6333, 50.0, '0.0.0.0')")
    
    try: cursor.execute("ALTER TABLE registros ADD COLUMN data_iso TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE registros ADD COLUMN foto BLOB")
    except: pass
    
    conn.commit()
    conn.close()

def get_ip_usuario():
    try: return requests.get('https://api.ipify.org', timeout=5).text
    except: return "Indisponível"

# --- INICIALIZAÇÃO ---
inicializar_banco()
conn = abrir_conexao()
conf = pd.read_sql_query("SELECT * FROM configuracoes WHERE id=1", conn).iloc[0]
lista_func = pd.read_sql_query("SELECT nome FROM funcionarios ORDER BY nome", conn)['nome'].tolist()
conn.close()

# --- INTERFACE DO FUNCIONÁRIO ---
st.title(f"🏢 {conf['nome_empresa']}")
st.subheader("Ponto Digital com GPS e Reconhecimento")

# Captura de Dados de Segurança
ip_atual = get_ip_usuario()
loc = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: pos.coords.latitude, lon: pos.coords.longitude}}, '*') })", key="get_location")

st.info(f"🌐 Rede: {ip_atual} | 📍 Status: {'GPS Localizado' if loc else 'Buscando GPS...'}")

usuario = st.selectbox("Selecione seu nome:", [""] + lista_func)

if usuario:
    # VALIDAÇÃO DE SEGURANÇA (IP e GPS)
    ip_valido = (conf['ip_loja'] == '0.0.0.0' or ip_atual == conf['ip_loja'])
    distancia = 999999
    if loc:
        distancia = geodesic((conf['lat'], conf['lon']), (loc['lat'], loc['lon'])).meters
    
    geo_valido = (distancia <= conf['raio_metros'])

    if not ip_valido:
        st.error(f"❌ Bloqueado: Você não está no Wi-Fi autorizado da empresa.")
    elif not loc:
        st.warning("⚠️ Aguardando sinal de GPS para liberar o ponto...")
    elif not geo_valido:
        st.error(f"❌ Fora do raio permitido! Você está a {int(distancia)}m da loja. Limite: {int(conf['raio_metros'])}m.")
    else:
        st.success("✅ Localização e Rede Confirmadas!")
        foto = st.camera_input("Capture sua foto para validar")
        
        if foto:
            c1, c2 = st.columns(2)
            fuso = pytz.timezone('America/Sao_Paulo')
            agora = datetime.now(fuso)
            
            def salvar(tipo):
                conn = abrir_conexao()
                img_bin = io.BytesIO(foto.getvalue()).getvalue()
                conn.execute("INSERT INTO registros (funcionario, tipo, data_hora, data_iso, foto) VALUES (?,?,?,?,?)",
                             (usuario, tipo, agora.strftime("%d/%m/%Y %H:%M:%S"), agora.date().isoformat(), img_bin))
                conn.commit()
                conn.close()
                st.success(f"Ponto de {tipo} registrado!")
                st.balloons()

            if c1.button("🚀 ENTRADA", use_container_width=True): salvar("Entrada")
            if c1.button("☕ SAÍDA ALMOÇO", use_container_width=True): salvar("Saída Almoço")
            if c2.button("🍱 VOLTA ALMOÇO", use_container_width=True): salvar("Volta Almoço")
            if c2.button("🏠 SAÍDA FINAL", use_container_width=True): salvar("Saída Final")

# --- PAINEL ADMINISTRATIVO ---
with st.sidebar:
    st.header("🔐 Gestão OrbTech")
    senha = st.text_input("Senha Admin", type="password")
    
    if senha == "1234":
        st.success("Painel Liberado")
        
        # 1. Configurações da Empresa
        with st.expander("🏢 Dados da Empresa & Trava"):
            n_empresa = st.text_input("Nome da Loja", value=conf['nome_empresa'])
            n_lat = st.number_input("Latitude Loja", value=conf['lat'], format="%.6f")
            n_lon = st.number_input("Longitude Loja", value=conf['lon'], format="%.6f")
            n_raio = st.number_input("Raio Permissão (m)", value=float(conf['raio_metros']))
            st.write(f"Seu IP atual: {ip_atual}")
            if st.button("Definir meu IP atual como o da Loja"):
                n_ip = ip_atual
            else: n_ip = conf['ip_loja']
            
            if st.button("Salvar Configurações"):
                conn = abrir_conexao()
                conn.execute("UPDATE configuracoes SET nome_empresa=?, lat=?, lon=?, raio_metros=?, ip_loja=? WHERE id=1",
                             (n_empresa, n_lat, n_lon, n_raio, n_ip))
                conn.commit()
                conn.close()
                st.rerun()

        # 2. Funcionários
        with st.expander("👤 Gerenciar Equipe"):
            novo_f = st.text_input("Novo Funcionário")
            if st.button("Adicionar"):
                conn = abrir_conexao()
                conn.execute("INSERT INTO funcionarios (nome) VALUES (?)", (novo_f,))
                conn.commit()
                conn.close()
                st.rerun()

        # 3. Relatórios
        with st.expander("📊 Relatórios"):
            if st.button("Gerar Espelho de Ponto Excel"):
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
                        ws['A2'] = f"RELATÓRIO GERADO EM: {datetime.now().strftime('%d/%m/%Y')}"
                        ws[f'A{len(esp)+7}'] = "___________ \n ASSINATURA COLABORADOR"
                    
                    st.download_button("⬇️ Baixar Planilha", output.getvalue(), f"ponto_{conf['nome_empresa']}.xlsx")

        # 4. Auditoria Visual
        with st.expander("📸 Últimas Fotos"):
            conn = abrir_conexao()
            fotos = pd.read_sql_query("SELECT funcionario, tipo, data_hora, foto FROM registros ORDER BY id DESC LIMIT 5", conn)
            conn.close()
            for _, r in fotos.iterrows():
                st.write(f"*{r['funcionario']}* - {r['tipo']}")
                if r['foto']: st.image(r['foto'], width=150)
