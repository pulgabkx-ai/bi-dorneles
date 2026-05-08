import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. FUNÇÕES DE DADOS (Máxima Resiliência)
@st.cache_resource
def conectar_google_sheets():
    """Conexão com retry agressivo para instabilidades de rede no Streamlit Cloud."""
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Tentaremos 5 vezes com intervalos crescentes
    for tentativa in range(5):
        try:
            info_chaves = dict(st.secrets["gcp_service_account"])
            if "private_key" in info_chaves:
                info_chaves["private_key"] = info_chaves["private_key"].replace("\\n", "\n")
                
            creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
            client = gspread.authorize(creds)
            
            url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
            return client.open_by_url(url_da_planilha).sheet1
            
        except Exception as e:
            if tentativa < 4:
                # Espera 2, 4, 6... segundos antes de tentar de novo
                time.sleep(2 * (tentativa + 1)) 
                continue
            else:
                st.error(f"Erro crítico de conexão: {e}")
                st.stop()

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    df.columns = df.columns.str.strip()
    
    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
                errors='coerce'
            ).fillna(0)
    
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# Inicialização
try:
    df_base = buscar_e_limpar_dados()
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# 3. BARRA LATERAL
st.sidebar.header("🎯 Painel de Controle")

data_min = df_base['Data de Entrada'].min().to_pydatetime()
data_max = df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

def criar_filtro(titulo, coluna):
    opcoes = sorted(df_base[coluna].unique().tolist())
    return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

sel_operadores = criar_filtro("Operadores", "Operador")
sel_status = criar_filtro("Status Atual", "Status")
sel_cidades = criar_filtro("Cidades", "Cidade")

# 4. FILTRAGEM
df_f = df_base.copy()
if len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[(df_f['Operador'].isin(sel_operadores)) & (df_f['Status'].isin(sel_status)) & (df_f['Cidade'].isin(sel_cidades))]

# 5. UI
st.title("📊 BI Dorneles Soluções")
tab_sucesso, tab_perdas, tab_ads = st.tabs(["🚀 Visão Geral", "🔍 Análise de Perdas", "📱 Meta Ads"])

with tab_sucesso:
    m1, m2, m3, m4 = st.columns(4)
    total_est = df_f['Valor Estimado'].sum()
    df_fechado = df_f[df_f['Status'].str.lower() == 'fechado']
    total_fat = df_fechado['Valor Final'].sum()
    
    m1.metric("Orçamentos Totais", f"R$ {total_est:,.2f}")
    m2.metric("Faturamento Real", f"R$ {total_fat:,.2f}", delta=f"{(total_fat/total_est*100 if total_est > 0 else 0):.1f}% conv.")
    m3.metric("Investimento Frete", f"R$ {df_f['Custo Frete'].sum():,.2f}")
    m4.metric("Ticket Médio", f"R$ {(total_fat/len(df_fechado) if len(df_fechado) > 0 else 0):,.2f}")

    col1, col2 = st.columns(2)
    with col1:
        df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        mapa_cores = {"Perdido": "#FF4B4B", "Fechado": "#2E8B57", "Em Aberto": "#1C83E1", "Orçamento Gerado": "#FACA2E"}
        fig_funnel = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status', color_discrete_map=mapa_cores)
        st.plotly_chart(fig_funnel, use_container_width=True)
    with col2:
        fig_op = px.bar(df_f.groupby('Operador')['Valor Final'].sum().reset_index(), x='Operador', y='Valor Final', text_auto='.2s', color_discrete_sequence=['#2E8B57'])
        st.plotly_chart(fig_op, use_container_width=True)

    st.subheader("📋 Detalhes dos Leads")
    st.dataframe(df_f[['Data de Entrada', 'Cliente', 'Status', 'Operador', 'Valor Estimado', 'Valor Final']], use_container_width=True, hide_index=True)

with tab_perdas:
    df_p = df_f[df_f['Status'].str.lower() == 'perdido']
    if df_p.empty:
        st.success("Nenhuma perda registrada!")
    else:
        st.header("❌ Análise de Desistências")
        cp1, cp2 = st.columns(2)
        with cp1:
            motivos = df_p[df_p['Motivo da Perda'].str.strip() != '']
            if not motivos.empty:
                fig_pie = px.pie(motivos, names='Motivo da Perda', values='Valor Estimado', hole=0.4, color_discrete_sequence=px.colors.sequential.Reds_r)
                st.plotly_chart(fig_pie, use_container_width=True)
        with cp2:
            fig_p_op = px.bar(df_p.groupby('Operador')['Valor Estimado'].sum().reset_index(), x='Operador', y='Valor Estimado', color_discrete_sequence=['#8B0000'])
            st.plotly_chart(fig_p_op, use_container_width=True)

with tab_ads:
    st.info("🚧 Módulo Meta Ads em desenvolvimento.")

st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
