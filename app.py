import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. FUNÇÕES DE DADOS (Otimizadas com Cache e Segurança)
@st.cache_resource
def conectar_google_sheets():
    """Conecta ao Google Sheets usando Secrets para maior segurança no Streamlit Cloud"""
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Prioriza Secrets (Nuvem), mas mantém suporte a arquivo local se disponível
    if "gcp_service_account" in st.secrets:
        info_chaves = dict(st.secrets["gcp_service_account"])
        # Limpeza da chave privada para evitar erro de assinatura JWT
        if "private_key" in info_chaves:
            pk = info_chaves["private_key"].strip().strip('"').strip("'")
            info_chaves["private_key"] = pk.replace("\\n", "\n")
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
    else:
        # Fallback para desenvolvimento local
        creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
    
    client = gspread.authorize(creds)
    url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
    return client.open_by_url(url_da_planilha).sheet1

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    """Busca dados da Dorneles Soluções e aplica tratamentos de negócio"""
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    
    if df.empty:
        return df

    # Limpeza de nomes de colunas (remove espaços extras que causam KeyError)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Garantia de existência de colunas críticas
    colunas_obrigatorias = ['Status', 'Valor Estimado', 'Valor Final', 'Custo Frete', 
                            'Operador', 'Data de Entrada', 'Cidade', 'Motivo da Perda']
    for col in colunas_obrigatorias:
        if col not in df.columns:
            df[col] = 0 if 'Valor' in col or 'Custo' in col else ""

    # Tratamento de Moeda (Converte R$ para Float)
    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0)
    
    # Tratamento de Datas
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    # Remove registros sem data para não quebrar os filtros
    df = df.dropna(subset=['Data de Entrada'])
    
    # Cálculo de Dias em Processo
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    
    return df

# Inicialização do carregamento
try:
    df_base = buscar_e_limpar_dados()
    if df_base.empty:
        st.warning("Nenhum dado encontrado na planilha.")
        st.stop()
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# 3. BARRA LATERAL - FILTROS
st.sidebar.header("🎯 Painel de Controle")

# Filtro de Período
data_min = df_base['Data de Entrada'].min().to_pydatetime()
data_max = df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

# Filtros Dinâmicos
def criar_filtro(titulo, coluna):
    opcoes = sorted(df_base[coluna].astype(str).unique().tolist())
    return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

sel_operadores = criar_filtro("Operadores", "Operador")
sel_status = criar_filtro("Status Atual", "Status")
sel_cidades = criar_filtro("Cidades", "Cidade")

# 4. LÓGICA DE FILTRAGEM
df_f = df_base.copy()
if isinstance(periodo, tuple) and len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[
    (df_f['Operador'].astype(str).isin(sel_operadores)) & 
    (df_f['Status'].astype(str).isin(sel_status)) & 
    (df_f['Cidade'].astype(str).isin(sel_cidades))
]

# 5. ESTRUTURA DE ABAS
st.title("📊 BI Dorneles Soluções")
tab_sucesso, tab_perdas, tab_ads = st.tabs(["🚀 Visão Geral", "🔍 Análise de Perdas", "📱 Meta Ads"])

# --- ABA 1: VISÃO GERAL ---
with tab_sucesso:
    m1, m2, m3, m4 = st.columns(4)
    
    total_est = df_f['Valor Estimado'].sum()
    df_fechado = df_f[df_f['Status'].astype(str).str.lower() == 'fechado']
    total_fat = df_fechado['Valor Final'].sum()
    total_frete = df_f['Custo Frete'].sum()
    
    m1.metric("Orçamentos Totais", f"R$ {total_est:,.2f}")
    m2.metric("Faturamento Real", f"R$ {total_fat:,.2f}", 
              delta=f"{(total_fat/total_est*100 if total_est > 0 else 0):.1f}% conv.")
    m3.metric("Investimento Frete", f"R$ {total_frete:,.2f}")
    m4.metric("Ticket Médio", f"R$ {(total_fat/len(df_fechado) if len(df_fechado) > 0 else 0):,.2f}")

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Funil de Vendas")
        df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        mapa_cores = {"Perdido": "#FF4B4B", "Fechado": "#2E8B57", "Em Aberto": "#1C83E1", "Orçamento Gerado": "#FACA2E"}
        fig_funnel = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status', color_discrete_map=mapa_cores)
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col2:
        st.subheader("🚀 Faturamento por Operador")
        df_op = df_f.groupby('Operador')['Valor Final'].sum().reset_index()
        fig_op = px.bar(df_op, x='Operador', y='Valor Final', text_auto='.2s', color_discrete_sequence=['#2E8B57'])
        st.plotly_chart(fig_op, use_container_width=True)

    st.subheader("📋 Detalhes dos Leads")
    col_vis = ['Data de Entrada', 'Cliente', 'Material Solicitado', 'Status', 'Operador', 'Valor Estimado', 'Valor Final', 'Dias em Processo']
    # Garante que apenas colunas existentes sejam exibidas
    col_vis_existentes = [c for c in col_vis if c in df_f.columns]
    st.dataframe(df_f[col_vis_existentes], use_container_width=True, hide_index=True)

# --- ABA 2: ANÁLISE DE PERDAS ---
with tab_perdas:
    df_p = df_f[df_f['Status'].astype(str).str.lower() == 'perdido']
    
    if df_p.empty:
        st.success("Nenhuma perda registrada no período selecionado!")
    else:
        st.header("❌ Análise de Desistências")
        cp1, cp2 = st.columns(2)
        
        with cp1:
            # Gráfico de Pizza de Motivos
            motivos = df_p[df_p['Motivo da Perda'].astype(str).str.strip() != '']
            if not motivos.empty:
                st.subheader("Por que perdemos? (R$)")
                fig_pie = px.pie(motivos, names='Motivo da Perda', values='Valor Estimado', 
                                 hole=0.4, color_discrete_sequence=px.colors.sequential.Reds_r)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.warning("Sem motivos de perda preenchidos na planilha.")
        
        with cp2:
            st.subheader("Perdas por Operador")
            df_p_op = df_p.groupby('Operador')['Valor Estimado'].sum().reset_index()
            fig_p_op = px.bar(df_p_op, x='Operador', y='Valor Estimado', color_discrete_sequence=['#8B0000'])
            st.plotly_chart(fig_p_op, use_container_width=True)

        st.subheader("📝 Lista de Oportunidades Perdidas")
        st.dataframe(df_p[['Data de Entrada', 'Cliente', 'Motivo da Perda', 'Valor Estimado', 'Operador']], 
                     use_container_width=True, hide_index=True)

# --- ABA 3: META ADS ---
with tab_ads:
    st.info("🚧 Módulo Meta Ads em desenvolvimento. Em breve teremos integração com dados de CPL e ROI.")

st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')} | BI Dorneles Soluções")
