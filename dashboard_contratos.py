import streamlit as st
import pandas as pd
import requests
import sqlite3
from datetime import datetime, date, timedelta
import io
import os

# Define que o banco SEMPRE será salvo na pasta onde este script estiver (em M:\Ferramentas\Python)
DIRETORIO_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DIRETORIO_SCRIPT, "nllc_governance.db")

# ==============================================================================
# CONFIGURAÇÃO GERAL DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Ecossistema NLLC - Governança e Gestão de Riscos",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# BANCO DE DADOS LOCAL (PERSISTÊNCIA NLLC / SQLite)
# ==============================================================================
DB_PATH = "nllc_governance.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        # 1. Metadados e Controle NLLC do Contrato
        c.execute("""
            CREATE TABLE IF NOT EXISTS nllc_contratos (
                id_contrato TEXT PRIMARY KEY,
                tipo_regime TEXT DEFAULT 'SERVICO_CONTINUO',
                tem_dedicacao_exclusiva INTEGER DEFAULT 0,
                data_base_reajuste TEXT,
                valor_aditado_acumulado REAL DEFAULT 0.0,
                publicado_pncp INTEGER DEFAULT 1,
                data_publicacao_pncp TEXT,
                tipo_garantia TEXT DEFAULT 'Não Exigida',
                valor_garantia REAL DEFAULT 0.0,
                vencimento_garantia TEXT,
                clausula_retomada INTEGER DEFAULT 0,
                conta_vinculada_ativa INTEGER DEFAULT 0,
                saldo_conta_vinculada REAL DEFAULT 0.0,
                status_gestao TEXT DEFAULT 'Vigente / Em Execução',
                gestor_nome TEXT DEFAULT 'Não Atribuído',
                fiscal_tecnico TEXT DEFAULT 'Não Atribuído',
                fiscal_administrativo TEXT DEFAULT 'Não Atribuído',
                anotacoes_gerais TEXT DEFAULT ''
            )
        """)
        
        # 2. Matriz de Riscos (Art. 103)
        c.execute("""
            CREATE TABLE IF NOT EXISTS nllc_matriz_riscos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_contrato TEXT,
                evento_risco TEXT,
                probabilidade TEXT,
                impacto TEXT,
                acao_mitigadora TEXT,
                responsavel TEXT,
                status_risco TEXT DEFAULT 'Monitorado'
            )
        """)
        
        # 3. Livro de Ocorrências Digital e Sanções (Arts. 117, §1º e 155-163)
        c.execute("""
            CREATE TABLE IF NOT EXISTS nllc_ocorrencias_sancoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_contrato TEXT,
                tipo_evento TEXT,
                data_registro TEXT,
                descricao TEXT,
                valor_glosa REAL DEFAULT 0.0,
                status_processo TEXT DEFAULT 'Registrado'
            )
        """)

        # 4. Medições e SLA / IMR (Art. 117, §3º e Art. 140)
        c.execute("""
            CREATE TABLE IF NOT EXISTS nllc_medicoes_imr (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_contrato TEXT,
                periodo_ref TEXT,
                sla_percentual REAL,
                valor_medido REAL,
                valor_glosado REAL,
                termo_provisorio_emitido INTEGER DEFAULT 0,
                data_emissao_termo TEXT
            )
        """)

        # 5. Regularidade Trabalhista e Fiscal DEMO (Art. 121)
        c.execute("""
            CREATE TABLE IF NOT EXISTS nllc_regularidade_trabalhista (
                id_contrato TEXT PRIMARY KEY,
                cnd_federal_valida INTEGER DEFAULT 1,
                cndt_valida INTEGER DEFAULT 1,
                fgts_valido INTEGER DEFAULT 1,
                folha_salarios_paga INTEGER DEFAULT 1,
                trava_liquidacao INTEGER DEFAULT 0
            )
        """)
        conn.commit()

init_db()

# Funções Auxiliares de Banco
def db_query(query, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(query, conn, params=params)

def db_execute(query, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()

# ==============================================================================
# CARREGAMENTO DA API DO COMPRASNET
# ==============================================================================
def converter_moeda(v):
    if not v or pd.isna(v): return 0.0
    try: return float(str(v).replace(".", "").replace(",", "."))
    except: return 0.0

@st.cache_data(ttl=300)
def fetch_comprasnet(uasg):
    url = f"https://contratos.comprasnet.gov.br/api/contrato/ug/{uasg}"
    try:
        resp = requests.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code == 200:
            dados = resp.json()
            lista = []
            hoje = datetime.now().date()
            for d in dados:
                forn = d.get("fornecedor", {}) or {}
                fim_vig = d.get("vigencia_fim")
                dias_rest = None
                if fim_vig:
                    try:
                        dt_fim = datetime.strptime(fim_vig, "%Y-%m-%d").date()
                        dias_rest = (dt_fim - hoje).days
                    except: pass
                
                lista.append({
                    "id": str(d.get("id")),
                    "numero": d.get("numero", "N/A"),
                    "processo": d.get("processo", "N/A"),
                    "fornecedor": forn.get("nome", "Não informado"),
                    "cnpj_cpf": forn.get("cnpj_cpf_idgener", "N/A"),
                    "modalidade": d.get("modalidade", "Pregão"),
                    "objeto": d.get("objeto", ""),
                    "vigencia_inicio": d.get("vigencia_inicio"),
                    "vigencia_fim": fim_vig,
                    "dias_restantes": dias_rest,
                    "valor_global": converter_moeda(d.get("valor_global")),
                    "valor_acumulado": converter_moeda(d.get("valor_acumulado")),
                    "links": d.get("links", {})
                })
            return pd.DataFrame(lista), None
        return pd.DataFrame(), f"Status API: {resp.status_code}"
    except Exception as e:
        return pd.DataFrame(), str(e)

# ==============================================================================
# SIDEBAR / CONTROLE GLOBAL
# ==============================================================================
st.sidebar.image("https://img.icons8.com/fluency/96/scales.png", width=64)
st.sidebar.title("Governança NLLC")
st.sidebar.caption("Lei Federal nº 14.133/2021")

uasg_input = st.sidebar.text_input("Código UASG / Unidade Gestora:", value="102110")

if st.sidebar.button("🔄 Sincronizar Bases"):
    st.cache_data.clear()
    st.rerun()

# Seletor RBAC de Perfil
st.sidebar.divider()
st.sidebar.markdown("### 👤 Segregação de Funções")
perfil_ativo = st.sidebar.radio(
    "Selecione seu Perfil / Visão de Trabalho:",
    [
        "🏛️ Alta Gestão & Ordenador de Despesas",
        "📢 Pregoeiro / Agente de Contratação",
        "👔 Gestor do Contrato (Art. 117)",
        "📐 Fiscal Técnico (Medição / IMR / OS)",
        "💼 Fiscal Administrativo (DEMO / Encargos)",
        "🛡️ Matriz de Riscos & Sanções (Art. 103)",
        "🔍 Raio-X Integrado & Auditoria"
    ]
)

# Carrega e unifica dados
df_api, erro_api = fetch_comprasnet(uasg_input)
df_meta = db_query("SELECT * FROM nllc_contratos")

if not df_api.empty:
    if not df_meta.empty:
        df_completo = df_api.merge(df_meta, left_on="id", right_on="id_contrato", how="left")
    else:
        df_completo = df_api.copy()
        for col in ["tipo_regime", "tem_dedicacao_exclusiva", "data_base_reajuste", "valor_aditado_acumulado",
                    "publicado_pncp", "tipo_garantia", "vencimento_garantia", "status_gestao", "gestor_nome",
                    "fiscal_tecnico", "fiscal_administrativo", "anotacoes_gerais"]:
            df_completo[col] = None

    # Defaults
    df_completo["tipo_regime"] = df_completo["tipo_regime"].fillna("SERVICO_CONTINUO")
    df_completo["tem_dedicacao_exclusiva"] = df_completo["tem_dedicacao_exclusiva"].fillna(0)
    df_completo["valor_aditado_acumulado"] = df_completo["valor_aditado_acumulado"].fillna(0.0)
    df_completo["publicado_pncp"] = df_completo["publicado_pncp"].fillna(1)
    df_completo["status_gestao"] = df_completo["status_gestao"].fillna("Vigente / Em Execução")
    df_completo["saldo_a_executar"] = df_completo["valor_global"] - df_completo["valor_acumulado"]
    df_completo["percentual_aditado"] = (df_completo["valor_aditado_acumulado"] / df_completo["valor_global"].replace(0, 1)) * 100
else:
    df_completo = pd.DataFrame()

hoje = datetime.now().date()

# ==============================================================================
# 1. PERFIL: ALTA GESTÃO & ORDENADOR DE DESPESAS
# ==============================================================================
if perfil_ativo == "🏛️ Alta Gestão & Ordenador de Despesas":
    st.title("🏛️ Painel Estratégico da Alta Gestão")
    st.caption("Visão Macrofinanceira, Riscos Globais e Governança de Gastos Públicos")
    
    if df_completo.empty:
        st.warning("Nenhum dado carregado.")
    else:
        total_global = df_completo["valor_global"].sum()
        total_pago = df_completo["valor_acumulado"].sum()
        total_saldo = df_completo["saldo_a_executar"].sum()
        perc_exec = (total_pago / total_global * 100) if total_global > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Carteira Total de Contratos", len(df_completo))
        c2.metric("Volume Global Comprometido", f"R$ {total_global:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        c3.metric("Executado / Liquidado", f"R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), f"{perc_exec:.1f}% Executado")
        c4.metric("Saldo Restante a Executar", f"R$ {total_saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
        st.divider()
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("📊 Distribuição por Modalidade de Licitação")
            st.bar_chart(df_completo["modalidade"].value_counts())
        
        with col_g2:
            st.subheader("🏷️ Regime de Execução (Art. 106/111)")
            st.bar_chart(df_completo["tipo_regime"].value_counts())

        st.subheader("⚠️ Painel Executivo de Riscos e Exceções")
        aditivos_criticos = df_completo[df_completo["percentual_aditado"] >= 20.0]
        vencendo_30d = df_completo[(df_completo["dias_restantes"] >= 0) & (df_completo["dias_restantes"] <= 30)]
        
        rx1, rx2 = st.columns(2)
        with rx1:
            st.markdown(f"**🚨 Contratos Próximos do Limite Legal de 25% de Aditivo (Art. 125):** `{len(aditivos_criticos)}`")
            if not aditivos_criticos.empty:
                st.dataframe(aditivos_criticos[["numero", "fornecedor", "valor_global", "percentual_aditado"]], hide_index=True)
            else:
                st.success("Nenhum contrato com aditivo acima de 20%.")
        with rx2:
            st.markdown(f"**⏰ Contratos Expirando nos Próximos 30 Dias:** `{len(vencendo_30d)}`")
            if not vencendo_30d.empty:
                st.dataframe(vencendo_30d[["numero", "fornecedor", "vigencia_fim", "dias_restantes"]], hide_index=True)
            else:
                st.success("Nenhum contrato em estado crítico de vigência.")

# ==============================================================================
# 2. PERFIL: PREGOEIRO / AGENTE DE CONTRATAÇÃO
# ==============================================================================
elif perfil_ativo == "📢 Pregoeiro / Agente de Contratação":
    st.title("📢 Visão: Pregoeiro & Agente de Contratação")
    st.caption("Fase de Transição, Eficácia no PNCP (Art. 94) e Atas de Registro de Preços (Art. 86)")

    tab_pncp, tab_arp = st.tabs(["🌐 Publicação e Eficácia (PNCP - Art. 94)", "📋 Atas de Registro de Preços (ARP)"])
    
    with tab_pncp:
        st.subheader("Monitoramento de Publicação Obrigatória no PNCP")
        st.info("💡 **Regra Jurídica (Art. 94):** A divulgação no Portal Nacional de Contratações Públicas (PNCP) é condição indispensável para a eficácia do contrato e seus aditamentos.")
        
        colunas_pncp = ["numero", "processo", "fornecedor", "valor_global", "publicado_pncp", "vigencia_inicio"]
        st.dataframe(df_completo[colunas_pncp], use_container_width=True, hide_index=True)
    
    with tab_arp:
        st.subheader("Controle de Saldos de Atas e Adesões ('Caronas' - Art. 86)")
        st.caption("Gestão de quantitativos registrados, consumo pelo órgão gerenciador e limites de adesão.")
        st.warning("Para contratos decorrentes de SRP, gerencie o limite de até 50% para caronas e o dobro do quantitativo total da ata.")
        # Exibição das modalidades de SRP
        arps = df_completo[df_completo["modalidade"].str.contains("Pregão|Registro", case=False, na=False)]
        st.dataframe(arps[["numero", "fornecedor", "objeto", "valor_global", "vigencia_fim"]], use_container_width=True, hide_index=True)

# ==============================================================================
# 3. PERFIL: GESTOR DO CONTRATO (Art. 117, caput)
# ==============================================================================
elif perfil_ativo == "👔 Gestor do Contrato (Art. 117)":
    st.title("👔 Painel do Gestor do Contrato")
    st.caption("Controle de Aditivos (Art. 125), Interregno de Reajuste/Repactuação (Art. 135/136) e Janela de Prorrogação")

    if not df_completo.empty:
        # Seletor do Contrato para Gestão
        opcoes = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
        sel_contrato = st.selectbox("Selecione o Contrato para Gestão Formal:", opcoes)
        id_sel = sel_contrato.split("ID: ")[-1].replace(")", "")
        item = df_completo[df_completo["id"] == id_sel].iloc[0]

        # 1. Alertas de Limites Legais e Prazos
        st.markdown(f"### 📑 Gestão do Contrato nº `{item['numero']}` — {item['fornecedor']}")
        
        g_c1, g_c2, g_c3 = st.columns(3)
        
        # Alerta de Aditivo (Art. 125)
        perc_adit = item["percentual_aditado"]
        limite_max = 50.0 if item["tipo_regime"] == "OBRA_ENGENHARIA" else 25.0
        g_c1.metric(
            "Aditivo Acumulado (Art. 125)",
            f"{perc_adit:.2f}%",
            f"Limite Legal: {limite_max:.0f}%",
            delta_color="inverse" if perc_adit >= 20.0 else "normal"
        )
        if perc_adit >= limite_max:
            st.error(f"🚨 **TRAVA LEGAL:** Contrato atingiu o limite de {limite_max}% de aditivos previsto no Art. 125 da Lei 14.133/2021.")
        elif perc_adit >= 20.0:
            st.warning(f"⚠️ **ATENÇÃO:** Contrato atingiu {perc_adit:.1f}% de aditivos (próximo do teto de {limite_max}%).")

        # Alerta de Reajuste / Repactuação Anual (Art. 135/136)
        dt_base = item["data_base_reajuste"]
        apto_reajuste = False
        dias_base = 0
        if dt_base:
            try:
                dt_obj = datetime.strptime(str(dt_base), "%Y-%m-%d").date()
                dias_base = (hoje - dt_obj).days
                apto_reajuste = dias_base >= 365
            except: pass

        g_c2.metric(
            "Interregno de Reajuste (Art. 135)",
            f"{dias_base} dias",
            "Apto a Reajuste / Repactuação" if apto_reajuste else "Interregno não completado",
            delta_color="normal" if apto_reajuste else "off"
        )

        # Alerta de Janela de Decisão de Prorrogação (120 dias - Art. 106/107)
        dias_venc = item["dias_restantes"] or 0
        janela_120d = (item["tipo_regime"] == "SERVICO_CONTINUO") and (0 <= dias_venc <= 120)
        g_c3.metric(
            "Janela de Prorrogação (120d)",
            f"{dias_venc} dias restantes",
            "🚨 Iniciar Processo de Prorrogação!" if janela_120d else "Vigência Regular",
            delta_color="inverse" if janela_120d else "normal"
        )

        st.divider()

        # Formulário de Atualização e Parametrização do Contrato
        with st.form(key=f"form_gestor_{id_sel}"):
            st.markdown("#### ⚙️ Parametrização Jurídica e Administrativa do Contrato")
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                novo_regime = st.selectbox(
                    "Tipo de Regime Contratual (NLLC):",
                    ["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"],
                    index=["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"].index(item["tipo_regime"]) if item["tipo_regime"] in ["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"] else 0
                )
                tem_demo = st.checkbox("Dedicação Exclusiva de Mão de Obra (DEMO)?", value=bool(item["tem_dedicacao_exclusiva"]))
                status_gest = st.selectbox(
                    "Status do Contrato:",
                    ["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"],
                    index=["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"].index(item["status_gestao"]) if item["status_gestao"] in ["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"] else 0
                )

            with col_f2:
                dt_base_val = date.today()
                if item["data_base_reajuste"]:
                    try: dt_base_val = datetime.strptime(str(item["data_base_reajuste"]), "%Y-%m-%d").date()
                    except: pass
                nova_dt_base = st.date_input("Data-Base do Reajuste / Proposta:", value=dt_base_val)
                novo_val_aditado = st.number_input("Valor Aditado Acumulado (R$):", value=float(item["valor_aditado_acumulado"]), min_value=0.0, format="%.2f")
                publicado_pncp_val = st.checkbox("Publicado no PNCP?", value=bool(item["publicado_pncp"]))

            with col_f3:
                nome_gestor = st.text_input("Gestor do Contrato (Portaria):", value=str(item["gestor_nome"]) if item["gestor_nome"] else "")
                nome_fisc_tec = st.text_input("Fiscal Técnico Designado:", value=str(item["fiscal_tecnico"]) if item["fiscal_tecnico"] else "")
                nome_fisc_adm = st.text_input("Fiscal Administrativo Designado:", value=str(item["fiscal_administrativo"]) if item["fiscal_administrativo"] else "")

            anotacoes_txt = st.text_area("Despachos e Anotações Gerais do Gestor:", value=str(item["anotacoes_gerais"]) if item["anotacoes_gerais"] else "")

            if st.form_submit_button("💾 Salvar Parametrização do Contrato"):
                db_execute("""
                    INSERT OR REPLACE INTO nllc_contratos 
                    (id_contrato, tipo_regime, tem_dedicacao_exclusiva, data_base_reajuste, valor_aditado_acumulado,
                     publicado_pncp, status_gestao, gestor_nome, fiscal_tecnico, fiscal_administrativo, anotacoes_gerais)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    id_sel, novo_regime, int(tem_demo), nova_dt_base.strftime("%Y-%m-%d"), novo_val_aditado,
                    int(publicado_pncp_val), status_gest, nome_gestor, nome_fisc_tec, nome_fisc_adm, anotacoes_txt
                ))
                st.success("✅ Parâmetros e limites atualizados com sucesso!")
                st.cache_data.clear()
                st.rerun()

# ==============================================================================
# 4. PERFIL: FISCAL TÉCNICO (Medição / SLA / IMR / Art. 117, §3º e Art. 140)
# ==============================================================================
elif perfil_ativo == "📐 Fiscal Técnico (Medição / IMR / OS)":
    st.title("📐 Painel do Fiscal Técnico")
    st.caption("Aferição de SLA/IMR, Glosas de Pagamento e Emissão de Termo de Recebimento Provisório (Art. 140)")

    if not df_completo.empty:
        opcoes_tec = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
        sel_tec = st.selectbox("Selecione o Contrato para Fiscalização Técnica:", opcoes_tec)
        id_tec = sel_tec.split("ID: ")[-1].replace(")", "")
        item_tec = df_completo[df_completo["id"] == id_tec].iloc[0]

        st.markdown(f"**Fiscal Técnico Atual:** `{item_tec['fiscal_tecnico']}` | **Objeto:** {item_tec['objeto']}")
        
        tab_medicao, tab_termo, tab_ocorrencias = st.tabs([
            "📊 Aferição de SLA / IMR e Medição",
            "📜 Termo de Recebimento Provisório (Art. 140)",
            "📖 Livro Digital de Ocorrências (Art. 117, §1º)"
        ])

        with tab_medicao:
            st.subheader("Lançar Medição Mensal e Glosas")
            with st.form(f"form_medicao_{id_tec}"):
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    periodo_ref = st.text_input("Mês/Ano de Referência:", placeholder="Ex: 08/2026")
                    sla_atingido = st.slider("Índice de Nível de Serviço (SLA / IMR) %:", 0.0, 100.0, 95.0)
                with mc2:
                    val_medido = st.number_input("Valor Bruto Medido (R$):", min_value=0.0, format="%.2f")
                    val_glosa = st.number_input("Valor Glosado por Inadimplemento (R$):", min_value=0.0, format="%.2f")
                with mc3:
                    termo_emit = st.checkbox("Emitir Termo Provisório nesta medição?", value=True)
                
                if st.form_submit_button("Salvar Medição Técnica"):
                    db_execute("""
                        INSERT INTO nllc_medicoes_imr (id_contrato, periodo_ref, sla_percentual, valor_medido, valor_glosado, termo_provisorio_emitido, data_emissao_termo)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (id_tec, periodo_ref, sla_atingido, val_medido, val_glosa, int(termo_emit), datetime.now().strftime("%Y-%m-%d")))
                    st.success("Medição e glosa registradas com sucesso!")
                    st.rerun()

            st.markdown("#### Histórico de Medições do Contrato")
            df_med = db_query("SELECT * FROM nllc_medicoes_imr WHERE id_contrato = ?", params=(id_tec,))
            st.dataframe(df_med, use_container_width=True, hide_index=True)

        with tab_termo:
            st.subheader("Termo de Recebimento Provisório Digital (Art. 140, I, 'a' e II, 'a')")
            st.info("O fiscal técnico tem prazo padrão de até 15 (quinze) dias para lavrar o Termo Provisório após a entrega/medição.")
            
            st.markdown(f"""
            > **TERMO DE RECEBIMENTO PROVISÓRIO**  
            > Declaramos que os serviços/bens relativos ao **Contrato nº {item_tec['numero']}**, fornecido por **{item_tec['fornecedor']}**, foram recebidos provisoriamente nesta data para efeito de posterior verificação da conformidade com as especificações contratuais e do IMR.  
            > **Data:** {datetime.now().strftime('%d/%m/%Y')} | **Fiscal Técnico:** {item_tec['fiscal_tecnico']}
            """)
            if st.button("🖨️ Registrar Emissão Formal do Termo Provisório"):
                st.success("Termo de Recebimento Provisório formalizado e registrado no histórico!")

        with tab_ocorrencias:
            st.subheader("Livro de Registro de Ocorrências Digital (Art. 117, § 1º)")
            with st.form("form_ocorrencia"):
                tipo_oc = st.selectbox("Tipo de Registro:", ["Notificação de Atraso", "Registro de Falha de Execução", "Descumprimento de SLA", "Elogio / Entrega Antecipada"])
                desc_oc = st.text_area("Descrição Fática da Ocorrência:")
                glosa_oc = st.number_input("Valor Estimado de Prejuízo/Glosa (R$):", min_value=0.0, format="%.2f")
                if st.form_submit_button("Adicionar Ocorrência no Livro Digital"):
                    db_execute("""
                        INSERT INTO nllc_ocorrencias_sancoes (id_contrato, tipo_evento, data_registro, descricao, valor_glosa, status_processo)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (id_tec, tipo_oc, datetime.now().strftime("%Y-%m-%d %H:%M"), desc_oc, glosa_oc, "Em Notificação"))
                    st.success("Ocorrência registrada no Livro Digital!")
                    st.rerun()

            df_oc = db_query("SELECT * FROM nllc_ocorrencias_sancoes WHERE id_contrato = ?", params=(id_tec,))
            st.dataframe(df_oc, use_container_width=True, hide_index=True)

# ==============================================================================
# 5. PERFIL: FISCAL ADMINISTRATIVO (DEMO / Encargos / Art. 121)
# ==============================================================================
elif perfil_ativo == "💼 Fiscal Administrativo (DEMO / Encargos)":
    st.title("💼 Painel do Fiscal Administrativo")
    st.caption("Fiscalização de Dedicação Exclusiva de Mão de Obra (DEMO), CNDs, Folha e Conta Vinculada (Art. 121)")

    if not df_completo.empty:
        opcoes_adm = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
        sel_adm = st.selectbox("Selecione o Contrato para Fiscalização Administrativa:", opcoes_adm)
        id_adm = sel_adm.split("ID: ")[-1].replace(")", "")
        item_adm = df_completo[df_completo["id"] == id_adm].iloc[0]

        df_reg = db_query("SELECT * FROM nllc_regularidade_trabalhista WHERE id_contrato = ?", params=(id_adm,))
        reg_atual = df_reg.iloc[0] if not df_reg.empty else None

        st.markdown(f"### 🛡️ Trava de Responsabilidade Subsidiária (Art. 121, § 2º)")
        st.warning("⚠️ **Regra Legal:** A liquidação e o pagamento da fatura estão condicionados à comprovação do recolhimento do FGTS, CNDT, INSS e quitação das verbas trabalhistas e salariais do mês anterior.")

        with st.form(f"form_fiscal_adm_{id_adm}"):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                cnd_fed = st.checkbox("CND Federal / Receita e PGFN Válida?", value=bool(reg_atual["cnd_federal_valida"]) if reg_atual is not None else True)
                cndt = st.checkbox("CNDT (Certidão Negativa Trabalhista) Válida?", value=bool(reg_atual["cndt_valida"]) if reg_atual is not None else True)
                fgts = st.checkbox("CRF / FGTS Regular?", value=bool(reg_atual["fgts_valido"]) if reg_atual is not None else True)
            with col_a2:
                folha = st.checkbox("Folha de Pagamento e Benefícios Quitados?", value=bool(reg_atual["folha_salarios_paga"]) if reg_atual is not None else True)
                trava = st.checkbox("🔒 TRAVAR LIQUIDAÇÃO / BLOQUEAR FATURA?", value=bool(reg_atual["trava_liquidacao"]) if reg_atual is not None else False)

            st.divider()
            st.markdown("#### 🏦 Monitoramento de Conta Vinculada / Fato Gerador (Férias, 13º e Rescisão)")
            c_cta1, c_cta2 = st.columns(2)
            with c_cta1:
                cta_ativa = st.checkbox("Utiliza Conta-Depósito Vinculada / Fato Gerador?", value=bool(item_adm.get("conta_vinculada_ativa", 0)))
            with c_cta2:
                saldo_cta = st.number_input("Saldo Provisionado em Conta Vinculada (R$):", value=float(item_adm.get("saldo_conta_vinculada", 0.0) or 0.0), min_value=0.0, format="%.2f")

            if st.form_submit_button("💾 Salvar Parecer da Fiscalização Administrativa"):
                db_execute("""
                    INSERT OR REPLACE INTO nllc_regularidade_trabalhista 
                    (id_contrato, cnd_federal_valida, cndt_valida, fgts_valido, folha_salarios_paga, trava_liquidacao)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (id_adm, int(cnd_fed), int(cndt), int(fgts), int(folha), int(trava)))
                
                db_execute("""
                    UPDATE nllc_contratos SET conta_vinculada_ativa = ?, saldo_conta_vinculada = ? WHERE id_contrato = ?
                """, (int(cta_ativa), saldo_cta, id_adm))
                
                st.success("Parecer da fiscalização administrativa registrado com sucesso!")
                st.rerun()

# ==============================================================================
# 6. MÓDULO: MATRIZ DE RISCOS & SANÇÕES (Arts. 103 e 155 a 163)
# ==============================================================================
elif perfil_ativo == "🛡️ Matriz de Riscos & Sanções (Art. 103)":
    st.title("🛡️ Matriz de Riscos e Processo Sancionador")
    st.caption("Gestão de Riscos do Contrato (Art. 103) e Processos Administrativos de Responsabilização (PAR - Arts. 155-163)")

    tab_risco, tab_garantias, tab_sancoes = st.tabs([
        "🎯 Matriz de Riscos (Art. 103)",
        "📄 Garantias Contratuais (Arts. 96-102)",
        "⚖️ Processo Sancionador & PAR (Arts. 155-163)"
    ])

    with tab_risco:
        st.subheader("Matriz de Riscos Alocados no Contrato")
        if not df_completo.empty:
            sel_r_contrato = st.selectbox("Selecione o Contrato para Gestão de Risco:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()])
            id_r_sel = sel_r_contrato.split("ID: ")[-1].replace(")", "")

            with st.form("form_novo_risco"):
                st.markdown("**Cadastrar Novo Evento de Risco:**")
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    ev_risco = st.text_input("Evento de Risco:", placeholder="Ex: Inadimplemento de encargos trabalhistas")
                    resp_risco = st.selectbox("Alocação do Risco (Responsável):", ["Contratada", "Administração Pública", "Compartilhado"])
                with rc2:
                    prob = st.selectbox("Probabilidade:", ["Baixa", "Média", "Alta"])
                    imp = st.selectbox("Impacto:", ["Baixo", "Médio", "Alto"])
                with rc3:
                    mitig = st.text_area("Ação Preventiva / Mitigadora:", placeholder="Ex: Exigência de CND mensal e retenção cautelar")

                if st.form_submit_button("Adicionar Risco à Matriz"):
                    db_execute("""
                        INSERT INTO nllc_matriz_riscos (id_contrato, evento_risco, probabilidade, impacto, acao_mitigadora, responsavel)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (id_r_sel, ev_risco, prob, imp, mitig, resp_risco))
                    st.success("Risco cadastrado na Matriz!")
                    st.rerun()

            df_matriz = db_query("SELECT * FROM nllc_matriz_riscos WHERE id_contrato = ?", params=(id_r_sel,))
            st.dataframe(df_matriz, use_container_width=True, hide_index=True)

    with tab_garantias:
        st.subheader("Dashboard de Garantias Contratuais (Arts. 96 a 102)")
        st.info("Monitore a vigência das apólices de Seguro-Garantia e Fiança Bancária para evitar apólices vencidas durante a vigência do contrato.")
        
        if not df_completo.empty:
            sel_g_contrato = st.selectbox("Contrato para Gestão de Garantia:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()], key="gar_sel")
            id_g_sel = sel_g_contrato.split("ID: ")[-1].replace(")", "")
            item_g = df_completo[df_completo["id"] == id_g_sel].iloc[0]

            with st.form("form_garantia"):
                gc1, gc2, gc3 = st.columns(3)
                with gc1:
                    tp_garantia = st.selectbox("Modalidade de Garantia (Art. 96, §1º):", ["Não Exigida", "Caução em Dinheiro", "Título da Dívida Pública", "Seguro-Garantia", "Fiança Bancária"])
                    val_gar = st.number_input("Valor da Garantia (R$):", value=float(item_g.get("valor_garantia", 0.0) or 0.0), min_value=0.0, format="%.2f")
                with gc2:
                    venc_gar = st.date_input("Vencimento da Apólice / Garantia:", value=date.today() + timedelta(days=365))
                    retomada = st.checkbox("Cláusula de Retomada / Step-in (Grandes Obras - Art. 102)?", value=bool(item_g.get("clausula_retomada", 0)))
                with gc3:
                    st.write("")
                
                if st.form_submit_button("Salvar Parâmetros de Garantia"):
                    db_execute("""
                        INSERT OR REPLACE INTO nllc_contratos (id_contrato, tipo_garantia, valor_garantia, vencimento_garantia, clausula_retomada)
                        VALUES (?, ?, ?, ?, ?)
                    """, (id_g_sel, tp_garantia, val_gar, venc_gar.strftime("%Y-%m-%d"), int(retomada)))
                    st.success("Garantia atualizada!")
                    st.rerun()

    with tab_sancoes:
        st.subheader("Processo Administrativo Sancionador (Arts. 155 a 163)")
        st.caption("Registro de Advertências, Multas, Impedimento de Licitar e Declaração de Inidoneidade.")
        df_todas_sancoes = db_query("SELECT * FROM nllc_ocorrencias_sancoes")
        st.dataframe(df_todas_sancoes, use_container_width=True, hide_index=True)

# ==============================================================================
# 7. RAIO-X INTEGRADO & AUDITORIA NLLC (API AO VIVO + EXPORTAÇÃO)
# ==============================================================================
elif perfil_ativo == "🔍 Raio-X Integrado & Auditoria":
    st.title("🔍 Raio-X Integrado & Auditoria NLLC")
    st.caption("Consulta em tempo real aos endpoints do Comprasnet e Exportação Gerencial Multi-Abas")

    if not df_completo.empty:
        sel_rx = st.selectbox("Escolha o Contrato:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()])
        id_rx = sel_rx.split("ID: ")[-1].replace(")", "")
        rx = df_completo[df_completo["id"] == id_rx].iloc[0]

        st.markdown(f"### Contrato nº `{rx['numero']}` — {rx['fornecedor']}")
        st.markdown(f"**Objeto:** {rx['objeto']}")

        # Subconsultas da API
        links = rx.get("links", {}) if isinstance(rx.get("links"), dict) else {}
        sub_c1, sub_c2, sub_c3 = st.tabs(["📦 Itens do Contrato", "💳 Faturas & Pagamentos", "👥 Fiscais & Responsáveis na API"])
        
        with sub_c1:
            if "itens" in links:
                try:
                    r = requests.get(links["itens"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    if r.status_code == 200 and r.json():
                        st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                    else: st.caption("Nenhum item discriminado.")
                except: st.caption("Erro ao carregar itens.")
        
        with sub_c2:
            if "faturas" in links:
                try:
                    r = requests.get(links["faturas"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    if r.status_code == 200 and r.json():
                        st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                    else: st.caption("Nenhuma fatura registrada.")
                except: st.caption("Erro ao carregar faturas.")

        with sub_c3:
            if "responsaveis" in links:
                try:
                    r = requests.get(links["responsaveis"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    if r.status_code == 200 and r.json():
                        st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                    else: st.caption("Nenhum responsável formalizado na API.")
                except: st.caption("Erro ao carregar responsáveis.")

        st.divider()
        st.subheader("📑 Exportação Consolidada de Auditoria (Excel)")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_completo.to_excel(writer, index=False, sheet_name='Contratos_Governança_NLLC')
            db_query("SELECT * FROM nllc_matriz_riscos").to_excel(writer, index=False, sheet_name='Matriz_Riscos')
            db_query("SELECT * FROM nllc_ocorrencias_sancoes").to_excel(writer, index=False, sheet_name='Livro_Ocorrencias_Sancoes')
            db_query("SELECT * FROM nllc_medicoes_imr").to_excel(writer, index=False, sheet_name='Medicoes_SLA')

        st.download_button(
            label="📥 Baixar Relatório Completo de Governança NLLC (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"auditoria_nllc_uasg_{uasg_input}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
