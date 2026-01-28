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

# 1. CONFIGURAÇÃO DA MARCA
st.set_page_config(page_title="OrbTech Ponto Flex", page_icon="🛡️", layout="centered")

def abrir_conexao():
    return sqlite3.connect('ponto_loja.db', check_same_thread=False)

def inicializar_banco():
    conn = abrir_conexao()
    cursor = conn.cursor()
    # Adicionada a coluna 'modo_trava' (GPS ou IP)
    cursor.execute('''CREATE TABLE IF NOT EXISTS configuracoes 
                      (id INTEGER PRIMARY KEY, nome_empresa TEXT, lat REAL, lon REAL, 
                       raio_metros REAL, ip_loja TEXT, modo_trava TEXT)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS registros (id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT, tipo TEXT, data_hora TEXT, data_iso TEXT, foto BLOB)')
    
    if cursor.execute("SELECT COUNT(*) FROM configuracoes").fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes VALUES (1, 'OrbTech Cliente', -23.5505, -46.6333, 50.0, '0.0.0.0', 'GPS')")
    
    # Garantir que a coluna modo_trava existe (Migração)
    try: cursor.execute("ALTER TABLE configuracoes ADD COLUMN modo_trava TEXT DEFAULT 'GPS'")
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

st.title(f"🏢 {conf['nome_empresa']}")
st.write(f"🔒 Segurança Ativa: **Modo {conf['modo_trava']}**")

# Captura de Segurança
ip_atual = get_ip_usuario()
loc = None
if conf['modo_trava'] == 'GPS':
    loc = streamlit_js_eval(js_expressions="new Promise((resolve, reject) => { navigator.geolocation.getCurrentPosition(pos => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}), err => reject(err), {enableHighAccuracy: true, timeout: 10000}) })", key="get_location")

usuario = st.selectbox("Selecione seu nome:", [""] + lista_func)

if usuario:
    # LÓGICA DE VALIDAÇÃO FLEXÍVEL
    autorizado = False
    
    if conf['modo_trava'] == 'IP':
        if ip_atual == conf['ip_loja'] or conf['ip_loja'] == '0.0.0.0':
            st.success("✅ Conectado à Rede Autorizada")
            autorizado = True
        else:
            st.error(f"❌ Fora da Rede! Conecte-se ao Wi-Fi da empresa. (IP: {ip_atual})")
            
    elif conf['modo_trava'] == 'GPS':
        if loc:
            distancia = geodesic((conf['lat'], conf['lon']), (loc['lat'], loc['lon'])).meters
            if distancia <= conf['raio_metros']:
                st.success(f"✅ Localização confirmada ({int(distancia)}m)")
                autorizado = True
            else:
                st.error(f"❌ Fora do Raio! Você está a {int(distancia)}m da loja.")
        else:
            st.warning("📡 Buscando sinal de GPS... Verifique se a localização está ativa.")

    if autorizado:
        foto = st.camera_input("Foto de Verificação")
        if foto:
            c1, c2 = st.columns(2)
            agora = datetime.now(pytz.timezone('America/Sao_Paulo'))
            
            def salvar(tipo):
                conn = abrir_conexao()
                img_bin = io.BytesIO(foto.getvalue()).getvalue()
                conn.execute("INSERT INTO registros (funcionario, tipo, data_hora, data_iso, foto) VALUES (?,?,?,?,?)",
                             (usuario, tipo, agora.strftime("%d/%m/%Y %H:%M:%S"), agora.date().isoformat(), img_bin))
                conn.commit()
                conn.close()
                st.success(f"Ponto de {tipo} registrado!")
            
            if c1.button("🚀 ENTRADA", use_container_width=True): salvar("Entrada")
            if c2.button("🏠 SAÍDA", use_container_width=True): salvar("Saída Final")

# --- PAINEL DO GERENTE ---
with st.sidebar:
    st.header("🔐 Admin OrbTech")
    if st.text_input("Senha Admin", type="password") == "1234":
        
        with st.expander("🛠️ Configurações de Trava"):
            modo = st.radio("Escolha o Modo de Segurança:", ["GPS", "IP"], index=0 if conf['modo_trava'] == 'GPS' else 1)
            
            if modo == "GPS":
                n_lat = st.number_input("Lat", value=conf['lat'], format="%.6f")
                n_lon = st.number_input("Lon", value=conf['lon'], format="%.6f")
                n_raio = st.number_input("Raio (m)", value=float(conf['raio_metros']))
                n_ip = conf['ip_loja']
            else:
                st.write(f"IP da Loja: {conf['ip_loja']}")
                if st.button("Usar meu IP atual"): n_ip = ip_atual
                else: n_ip = conf['ip_loja']
                n_lat, n_lon, n_raio = conf['lat'], conf['lon'], conf['raio_metros']
            
            if st.button("Aplicar Mudanças"):
                conn = abrir_conexao()
                conn.execute("UPDATE configuracoes SET lat=?, lon=?, raio_metros=?, ip_loja=?, modo_trava=? WHERE id=1",
                             (n_lat, n_lon, n_raio, n_ip, modo))
                conn.commit()
                conn.close()
                st.rerun()

        # ABA: CADASTRAR
        st.divider()
        st.subheader("👤 Gestão de Equipe")
        novo_nome = st.text_input("Nome Completo")
        if st.button("Cadastrar Funcionário"):
            if novo_nome:
                conn = abrir_conexao()
                try:
                    conn.execute("INSERT INTO funcionarios (nome) VALUES (?)", (novo_nome,))
                    conn.commit()
                    st.success("Cadastrado!")
                    st.rerun()
                except: st.error("Erro: Nome já existe.")
                finally: conn.close()
                        # ABA: RELATÓRIOS
        st.divider()
        st.subheader("📊 Espelho de Ponto")
        if st.button("Gerar Relatório Excel"):
            conn = abrir_conexao()
            df = pd.read_sql_query("SELECT funcionario, tipo, data_iso, data_hora FROM registros", conn)
            conn.close()
            if not df.empty:
                df['data_hora'] = pd.to_datetime(df['data_hora'], format='%d/%m/%Y %H:%M:%S')
                espelho = df.pivot_table(index=['funcionario', 'data_iso'], columns='tipo', values='data_hora', aggfunc='first').reset_index()
                
                # Cálculo de Horas Extras
                for col in ['Entrada', 'Saída Almoço', 'Volta Almoço', 'Saída Final']:
                    if col not in espelho: espelho[col] = pd.NaT

                def calc_horas(row):
                    try:
                        manha = (row['Saída Almoço'] - row['Entrada']).total_seconds() / 3600
                        tarde = (row['Saída Final'] - row['Volta Almoço']).total_seconds() / 3600
                        total = manha + tarde
                        extra = max(0, total - 8.0)
                        return pd.Series([round(total, 2), round(extra, 2)])
                    except: return pd.Series([0.0, 0.0])

                espelho[['Total Horas', 'Horas Extras']] = espelho.apply(calc_horas, axis=1)
                
                output = io.BytesIO()
                espelho.to_excel(output, index=False)
                st.download_button("⬇️ Baixar Planilha (.xlsx)", data=output.getvalue(), file_name="relatorio_orbtech.xlsx")
            else: st.info("Sem dados.")

        # ABA: FOTOS
        st.divider()
        st.subheader("📸 Auditoria Visual")
        if st.button("Ver Últimas Fotos"):
            conn = abrir_conexao()
            fotos_df = pd.read_sql_query("SELECT funcionario, tipo, data_hora, foto FROM registros ORDER BY id DESC LIMIT 5", conn)
            conn.close()
            for _, row in fotos_df.iterrows():
                st.write(f"*{row['funcionario']}* ({row['tipo']})")
                st.caption(row['data_hora'])
                if row['foto']: st.image(row['foto'], width=150)
                st.divider()
