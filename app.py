import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
import streamlit_authenticator as stauth
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA (Deve ser a primeira linha) ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# --- 2. SISTEMA DE LOGIN ---
# Substitua os campos 'password' pelos hashes ($2b$12$...) gerados no Colab
credentials = {
    "usernames": {
        "luis": {
            "name": "Luis",
            "password": "$2b$12$0OC47bRbgIwsRTVznb8bMe0YrHFDFimg.1s9nYGFNc7fJdVu4uIRG" 
        },
        "dani": {
            "name": "Dani",
            "password": "$2b$12$cD.FBrKO6vTgNt.9tcbqR.7Tp1FBB8ZRcB79RXf.iaOk9K6J.FOzy"
        }
    }
}

authenticator = stauth.Authenticate(
    credentials,
    "dorneles_bi_cookie",
    "chave_secreta_dorneles",
    cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login('Acesso Restrito - Dorneles Soluções', 'main')

# --- 3. LÓGICA DE EXIBIÇÃO PÓS-LOGIN ---
if authentication_status:
    # Barra Lateral: Identificação e Logout
    authenticator.logout('Sair do Sistema', 'sidebar')
    st.sidebar.write(f"Usuário: **{name}**")

    # Função Auxiliar para Formatação de Moeda Brasileira
    def formatar_brl(valor):
        """Converte float para string no padrão R$ 1.234,56"""
        try:
            return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except:
            return "R$ 0,00"

    # --- 4. FUNÇÕES DE DADOS (Com Cache e Segurança) ---
    @st.cache_resource
    def conectar_google_sheets():
        """Conecta ao Google Sheets usando Secrets ou arquivo local"""
        escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        if "gcp_service_account" in st.secrets:
            info_chaves = dict(st.secrets["gcp_service_account"])
            if "private_key" in info_chaves:
                pk = info_chaves["private_key"].strip().strip('"').strip("'")
                info_chaves["private_key"] = pk.replace("\\n", "\n")
            info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
        else:
            creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
        
        client = gspread.authorize(creds)
        url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_da_planilha).sheet1

    @st.cache_data(ttl=60)
    def buscar_e_limpar_dados():
        """Busca dados e aplica tratamentos de moeda e data"""
        aba = conectar_google_sheets()
        df = pd.DataFrame(aba.get_all_records())
        
        if df.empty:
            return df

        # Limpeza de nomes de colunas
        df.columns = [str(col).strip() for col in df.columns]
        
        # Tratamento de Moeda (Converte R$ texto para Float para cálculos)
        colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
        for col in colunas_moeda:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
                    errors='coerce'
                ).fillna(0)
        
        # Tratamento de Datas
        df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
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

    # --- 5. BARRA LATERAL - FILTROS ---
    st.sidebar.header("🎯 Painel de Controle")

    data_min = df_base['Data de Entrada'].min().to_pydatetime()
    data_max = df_base['Data de Entrada'].max().to_pydatetime()
    periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

    def criar_filtro(titulo, coluna):
        opcoes = sorted(df_base[coluna].astype(str).unique().tolist())
        return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

    sel_operadores = criar_filtro("Operadores", "Operador")
    sel_status = criar_filtro("Status Atual", "Status")
    sel_cidades = criar_filtro("Cidades", "Cidade")

    # Lógica de Filtragem
    df_f = df_base.copy()
    if isinstance(periodo, tuple) and len(periodo) == 2:
        df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

    df_f = df_f[
        (df_f['Operador'].astype(str).isin(sel_operadores)) & 
        (df_f['Status'].astype(str).isin(sel_status)) & 
        (df_f['Cidade'].astype(str).isin(sel_cidades))
    ]

    # --- 6. INTERFACE DO DASHBOARD ---
    st.title("📊 BI Dorneles Soluções")
    tab_sucesso, tab_perdas, tab_ads = st.tabs(["🚀 Visão Geral", "🔍 Análise de Perdas", "📱 Meta Ads"])

    # --- ABA 1: VISÃO GERAL ---
    with tab_sucesso:
        m1, m2, m3, m4 = st.columns(4)
        
        total_est = df_f['Valor Estimado'].sum()
        df_fechado = df_f[df_f['Status'].astype(str).str.lower() == 'fechado']
        total_fat = df_fechado['Valor Final'].sum()
        total_frete = df_f['Custo Frete'].sum()
        
        # Métricas com formatação de moeda BR
        m1.metric("Orçado Total", formatar_brl(total_est))
        m2.metric("Faturamento Real", formatar_brl(total_fat), 
                  delta=f"{(total_fat/total_est*100 if total_est > 0 else 0):.1f}% conv.")
        m3.metric("Investimento Frete", formatar_brl(total_frete))
        m4.metric("Ticket Médio", formatar_brl(total_fat/len(df_fechado) if len(df_fechado) > 0 else 0))

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🎯 Funil de Vendas (R$)")
            df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
            fig_funnel = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status')
            st.plotly_chart(fig_funnel, use_container_width=True)

        with col2:
            st.subheader("🚀 Faturamento por Operador")
            df_op = df_f.groupby('Operador')['Valor Final'].sum().reset_index()
            fig_op = px.bar(df_op, x='Operador', y='Valor Final', text_auto='.2s', color_discrete_sequence=['#2E8B57'])
            st.plotly_chart(fig_op, use_container_width=True)

        st.subheader("📋 Detalhes dos Leads")
        # Criamos uma cópia para formatar as colunas da tabela sem afetar os cálculos
        df_display = df_f.copy()
        for col_moeda in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
            if col_moeda in df_display.columns:
                df_display[col_moeda] = df_display[col_moeda].apply(formatar_brl)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    # --- ABA 2: ANÁLISE DE PERDAS ---
    with tab_perdas:
        df_p = df_f[df_f['Status'].astype(str).str.lower() == 'perdido']
        if df_p.empty:
            st.success("Nenhuma perda registrada no período selecionado!")
        else:
            st.header("❌ Análise de Desistências")
            cp1, cp2 = st.columns(2)
            with cp1:
                st.subheader("Por que perdemos? (R$)")
                fig_pie = px.pie(df_p, names='Motivo da Perda', values='Valor Estimado', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            with cp2:
                st.subheader("Perdas por Operador")
                df_p_op = df_p.groupby('Operador')['Valor Estimado'].sum().reset_index()
                st.plotly_chart(px.bar(df_p_op, x='Operador', y='Valor Estimado'), use_container_width=True)

    # --- ABA 3: META ADS ---
    with tab_ads:
        st.info("🚧 Módulo Meta Ads em desenvolvimento.")

    st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')} | BI Dorneles Soluções")

# --- 7. MENSAGENS DE ERRO/AVISO DE LOGIN ---
elif authentication_status == False:
    st.error('Usuário ou senha incorretos.')
elif authentication_status == None:
    st.warning('Por favor, insira suas credenciais para acessar o BI.')
