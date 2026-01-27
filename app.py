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
st.set_page_config(page_title="OrbTech Ponto Pro 2026", page_icon="📍", layout="centered")

def abrir_conexao():
    return sqlite3.connect('ponto_loja.db', check_same_thread=False)

def inicializar_banco():
    conn = abrir_conexao()
    cursor = conn.cursor()
    # Tabela de Funcionários
    cursor.execute('CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)')
    # Tabela de Registros (com colunas para foto e data_iso)
    cursor.execute('''CREATE TABLE IF NOT EXISTS registros 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT, tipo TEXT, 
                       data_hora TEXT, data_iso TEXT, foto BLOB)''')
    # Tabela de Configurações GPS
    cursor.execute('CREATE TABLE IF NOT EXISTS configuracoes (id INTEGER PRIMARY KEY, lat REAL, lon REAL, raio_metros REAL)')
    
    # Adiciona colunas se não existirem (Migração automática)
    try: cursor.execute("ALTER TABLE registros ADD COLUMN data_iso TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE registros ADD COLUMN foto BLOB")
    except: pass

    # Configuração Inicial de GPS (Centro de SP como exemplo)
    cursor.execute("SELECT COUNT(*) FROM configuracoes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO configuracoes VALUES (1, -23.5505, -46.6333, 50.0)")
    
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
        
        # Converter Foto
        img = Image.open(foto_capturada)
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        
        cursor.execute("INSERT INTO registros (funcionario, tipo, data_hora, data_iso, foto) VALUES (?, ?, ?, ?, ?)", 
                       (nome, tipo, data_txt, data_iso, buf.getvalue()))
        conn.commit()
        conn.close()
        st.success(f"✅ {tipo} registrado com sucesso!")
        st.balloons()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# INICIALIZAÇÃO
inicializar_banco()
conn = abrir_conexao()
loja_config = pd.read_sql_query("SELECT lat, lon, raio_metros FROM configuracoes WHERE id=1", conn).iloc[0]
lista_func = pd.read_sql_query("SELECT nome FROM funcionarios ORDER BY nome", conn)['nome'].tolist()
conn.close()

# --- INTERFACE DO FUNCIONÁRIO ---
st.title("📍 OrbTech Ponto Pro")
st.write("Validação por Localização e Foto")

# Captura GPS via Browser
loc = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: pos.coords.latitude, lon: pos.coords.longitude}}, '*') })", key="get_location")

usuario = st.selectbox("Selecione seu nome:", [""] + lista_func)

if usuario:
    if loc:
        distancia = geodesic((loja_config['lat'], loja_config['lon']), (loc['lat'], loc['lon'])).meters
        
        if distancia <= loja_config['raio_metros']:
            st.success(f"📍 Localização confirmada! ({int(distancia)}m da loja)")
            foto = st.camera_input("Tire uma foto para registrar")
            
            if foto:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚀 ENTRADA", use_container_width=True): registrar_ponto_completo(usuario, "Entrada", foto)
                    if st.button("☕ SAÍDA ALMOÇO", use_container_width=True): registrar_ponto_completo(usuario, "Saída Almoço", foto)
                with c2:
                    if st.button("🍱 VOLTA ALMOÇO", use_container_width=True): registrar_ponto_completo(usuario, "Volta Almoço", foto)
                    if st.button("🏠 SAÍDA FINAL", use_container_width=True): registrar_ponto_completo(usuario, "Saída Final", foto)
        else:
            st.error(f"❌ Fora do raio permitido! Distância: {int(distancia)}m. Limite: {int(loja_config['raio_metros'])}m.")
    else:
        st.warning("Aguardando sinal do GPS... Ative a localização do seu celular.")

# --- PAINEL DO GERENTE (SIDEBAR) ---
with st.sidebar:
    st.header("🔐 Administração OrbTech")
    senha = st.text_input("Senha Admin", type="password")
    
    if senha == "1234":
        st.success("Acesso Liberado")
        
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

        # ABA: CONFIG GPS
        st.divider()
        st.subheader("📍 Localização da Loja")
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
