import streamlit as st
import pandas as pd
import requests
import sqlite3
from datetime import datetime, date, timedelta
import io

# ==============================================================================
# CONFIGURAÇÃO GERAL DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Ecossistema NLLC - Governança e Gestão de Riscos",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicialização de variáveis de sessão
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["perfil"] = None
    st.session_state["nome_usuario"] = ""

# ==============================================================================
# TELA 1: LOGIN (ISOLADA - SE NÃO ESTIVER AUTENTICADO)
# ==============================================================================
def render_tela_login():
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>🔒 Central de Gestão e Contratos NLLC</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Acesso restrito a servidores autorizados da Autarquia.</p>", unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        with st.form("form_login"):
            usuario = st.text_input("Usuário / Matrícula:")
            senha = st.text_input("Senha de Acesso:", type="password")
            btn_entrar = st.form_submit_button("🔓 Acessar Sistema", use_container_width=True)

            if btn_entrar:
                # Busca do cofre Secrets do Streamlit Cloud ou usa senhas padrão
                usuarios_validos = st.secrets.get("usuarios", {
                    "gestor": {"senha": "123", "perfil": "editor", "nome": "Francisco (Gestor)"},
                    "diretoria": {"senha": "456", "perfil": "leitor", "nome": "Gabinete da Diretoria"}
                })

                if usuario in usuarios_validos and str(senha) == str(usuarios_validos[usuario]["senha"]):
                    st.session_state["autenticado"] = True
                    st.session_state["perfil"] = usuarios_validos[usuario]["perfil"]
                    st.session_state["nome_usuario"] = usuarios_validos[usuario]["nome"]
                    st.success(f"Autenticado com sucesso! Carregando...")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos. Acesso negado.")

# ==============================================================================
# TELA 2: PAINEL COMPLETO (SÓ EXECUTA APÓS LOGIN CORRETO)
# ==============================================================================
def render_painel_principal():
    perfil_usuario = st.session_state["perfil"]
    nome_usuario = st.session_state["nome_usuario"]

    # Barra lateral
    st.sidebar.markdown(f"👤 Servidor: **{nome_usuario}**")
    if perfil_usuario == "editor":
        st.sidebar.success("🔑 Perfil: **Gestor (Edição Liberada)**")
    else:
        st.sidebar.info("👁️ Perfil: **Diretoria (Somente Leitura)**")

    if st.sidebar.button("🚪 Sair do Sistema"):
        st.session_state["autenticado"] = False
        st.session_state["perfil"] = None
        st.session_state["nome_usuario"] = ""
        st.rerun()

    # Banco SQLite
    DB_PATH = "nllc_governance.db"
    def init_db():
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
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

    def db_query(query, params=()):
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql(query, conn, params=params)

    def db_execute(query, params=()):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()

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
                hoje_dt = datetime.now().date()
                for d in dados:
                    forn = d.get("fornecedor", {}) or {}
                    fim_vig = d.get("vigencia_fim")
                    dias_rest = None
                    if fim_vig:
                        try:
                            dt_fim = datetime.strptime(fim_vig, "%Y-%m-%d").date()
                            dias_rest = (dt_fim - hoje_dt).days
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

    # Controles da barra lateral
    st.sidebar.divider()
    uasg_input = st.sidebar.text_input("Código UASG / UG:", value="102110")

    if st.sidebar.button("🔄 Sincronizar Bases"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.divider()
    perfil_ativo = st.sidebar.radio(
        "Visão de Trabalho (RBAC NLLC):",
        [
            "🏛️ Alta Gestão & Ordenador de Despesas",
            "👔 Gestor do Contrato (Art. 117)",
            "📐 Fiscal Técnico (Medição / IMR / OS)",
            "💼 Fiscal Administrativo (DEMO / Encargos)",
            "🛡️ Matriz de Riscos & Sanções (Art. 103)",
            "🔍 Raio-X Integrado & Auditoria"
        ]
    )

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

    # 1. ALTA GESTÃO
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

    # 2. GESTOR DO CONTRATO
    elif perfil_ativo == "👔 Gestor do Contrato (Art. 117)":
        st.title("👔 Painel do Gestor do Contrato")
        if not df_completo.empty:
            opcoes = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
            sel_contrato = st.selectbox("Selecione o Contrato para Gestão Formal:", opcoes)
            id_sel = sel_contrato.split("ID: ")[-1].replace(")", "")
            item = df_completo[df_completo["id"] == id_sel].iloc[0]

            g_c1, g_c2, g_c3 = st.columns(3)
            perc_adit = item["percentual_aditado"]
            limite_max = 50.0 if item["tipo_regime"] == "OBRA_ENGENHARIA" else 25.0
            g_c1.metric("Aditivo Acumulado (Art. 125)", f"{perc_adit:.2f}%", f"Limite Legal: {limite_max:.0f}%", delta_color="inverse" if perc_adit >= 20.0 else "normal")

            dt_base = item["data_base_reajuste"]
            dias_base = (hoje - datetime.strptime(str(dt_base), "%Y-%m-%d").date()).days if dt_base else 0
            g_c2.metric("Interregno de Reajuste (Art. 135)", f"{dias_base} dias", "Apto a Reajuste" if dias_base >= 365 else "Aguardando 1 ano")

            dias_venc = item["dias_restantes"] or 0
            janela_120d = (item["tipo_regime"] == "SERVICO_CONTINUO") and (0 <= dias_venc <= 120)
            g_c3.metric("Janela de Prorrogação (120d)", f"{dias_venc} dias restantes", "🚨 Iniciar Prorrogação!" if janela_120d else "Regular")

            st.divider()
            with st.form(key=f"form_gestor_{id_sel}"):
                st.markdown("#### ⚙️ Parametrização Jurídica e Administrativa do Contrato")
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    novo_regime = st.selectbox("Tipo de Regime:", ["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"], index=["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"].index(item["tipo_regime"]) if item["tipo_regime"] in ["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"] else 0)
                    tem_demo = st.checkbox("Dedicação Exclusiva (DEMO)?", value=bool(item["tem_dedicacao_exclusiva"]))
                    status_gest = st.selectbox("Status:", ["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"], index=["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"].index(item["status_gestao"]) if item["status_gestao"] in ["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"] else 0)
                with col_f2:
                    dt_base_val = date.today()
                    if item["data_base_reajuste"]:
                        try: dt_base_val = datetime.strptime(str(item["data_base_reajuste"]), "%Y-%m-%d").date()
                        except: pass
                    nova_dt_base = st.date_input("Data-Base do Reajuste:", value=dt_base_val)
                    novo_val_aditado = st.number_input("Valor Aditado Acumulado (R$):", value=float(item["valor_aditado_acumulado"]), min_value=0.0, format="%.2f")
                    publicado_pncp_val = st.checkbox("Publicado no PNCP?", value=bool(item["publicado_pncp"]))
                with col_f3:
                    nome_gestor = st.text_input("Gestor:", value=str(item["gestor_nome"]) if item["gestor_nome"] else "")
                    nome_fisc_tec = st.text_input("Fiscal Técnico:", value=str(item["fiscal_tecnico"]) if item["fiscal_tecnico"] else "")
                    nome_fisc_adm = st.text_input("Fiscal Administrativo:", value=str(item["fiscal_administrativo"]) if item["fiscal_administrativo"] else "")

                anotacoes_txt = st.text_area("Despachos e Anotações:", value=str(item["anotacoes_gerais"]) if item["anotacoes_gerais"] else "")

                if perfil_usuario == "editor":
                    if st.form_submit_button("💾 Salvar Parametrização"):
                        db_execute("""
                            INSERT OR REPLACE INTO nllc_contratos 
                            (id_contrato, tipo_regime, tem_dedicacao_exclusiva, data_base_reajuste, valor_aditado_acumulado,
                             publicado_pncp, status_gestao, gestor_nome, fiscal_tecnico, fiscal_administrativo, anotacoes_gerais)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (id_sel, novo_regime, int(tem_demo), nova_dt_base.strftime("%Y-%m-%d"), novo_val_aditado,
                              int(publicado_pncp_val), status_gest, nome_gestor, nome_fisc_tec, nome_fisc_adm, anotacoes_txt))
                        st.success("✅ Salvo com sucesso!")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.info("🔒 **Modo Somente Leitura:** Alterações desabilitadas para a Diretoria.")

    # 3. FISCAL TÉCNICO
    elif perfil_ativo == "📐 Fiscal Técnico (Medição / IMR / OS)":
        st.title("📐 Painel do Fiscal Técnico")
        if not df_completo.empty:
            opcoes_tec = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
            sel_tec = st.selectbox("Selecione o Contrato:", opcoes_tec)
            id_tec = sel_tec.split("ID: ")[-1].replace(")", "")

            with st.form(f"form_medicao_{id_tec}"):
                mc1, mc2 = st.columns(2)
                with mc1:
                    periodo_ref = st.text_input("Mês/Ano Ref:", placeholder="Ex: 08/2026")
                    sla_atingido = st.slider("SLA / IMR Atingido %:", 0.0, 100.0, 95.0)
                with mc2:
                    val_medido = st.number_input("Valor Bruto Medido (R$):", min_value=0.0, format="%.2f")
                    val_glosa = st.number_input("Valor Glosado (R$):", min_value=0.0, format="%.2f")
                
                if perfil_usuario == "editor":
                    if st.form_submit_button("Salvar Medição Técnica"):
                        db_execute("""
                            INSERT INTO nllc_medicoes_imr (id_contrato, periodo_ref, sla_percentual, valor_medido, valor_glosado, termo_provisorio_emitido, data_emissao_termo)
                            VALUES (?, ?, ?, ?, ?, 1, ?)
                        """, (id_tec, periodo_ref, sla_atingido, val_medido, val_glosa, datetime.now().strftime("%Y-%m-%d")))
                        st.success("Medição registrada!")
                        st.rerun()
                else:
                    st.info("🔒 Modo Somente Leitura.")

            df_med = db_query("SELECT * FROM nllc_medicoes_imr WHERE id_contrato = ?", params=(id_tec,))
            st.dataframe(df_med, use_container_width=True, hide_index=True)

    # 4. FISCAL ADMINISTRATIVO
    elif perfil_ativo == "💼 Fiscal Administrativo (DEMO / Encargos)":
        st.title("💼 Painel do Fiscal Administrativo")
        if not df_completo.empty:
            opcoes_adm = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
            sel_adm = st.selectbox("Selecione o Contrato:", opcoes_adm)
            id_adm = sel_adm.split("ID: ")[-1].replace(")", "")
            df_reg = db_query("SELECT * FROM nllc_regularidade_trabalhista WHERE id_contrato = ?", params=(id_adm,))
            reg_atual = df_reg.iloc[0] if not df_reg.empty else None

            with st.form(f"form_fiscal_adm_{id_adm}"):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    cnd_fed = st.checkbox("CND Federal Válida?", value=bool(reg_atual["cnd_federal_valida"]) if reg_atual is not None else True)
                    cndt = st.checkbox("CNDT Válida?", value=bool(reg_atual["cndt_valida"]) if reg_atual is not None else True)
                    fgts = st.checkbox("FGTS / CRF Regular?", value=bool(reg_atual["fgts_valido"]) if reg_atual is not None else True)
                with col_a2:
                    folha = st.checkbox("Folha Salarial Paga?", value=bool(reg_atual["folha_salarios_paga"]) if reg_atual is not None else True)
                    trava = st.checkbox("🔒 BLOQUEAR / TRAVAR LIQUIDAÇÃO?", value=bool(reg_atual["trava_liquidacao"]) if reg_atual is not None else False)

                if perfil_usuario == "editor":
                    if st.form_submit_button("💾 Salvar Parecer Fiscal"):
                        db_execute("""
                            INSERT OR REPLACE INTO nllc_regularidade_trabalhista 
                            (id_contrato, cnd_federal_valida, cndt_valida, fgts_valido, folha_salarios_paga, trava_liquidacao)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (id_adm, int(cnd_fed), int(cndt), int(fgts), int(folha), int(trava)))
                        st.success("Parecer atualizado!")
                        st.rerun()
                else:
                    st.info("🔒 Modo Somente Leitura.")

    # 5. MATRIZ DE RISCOS
    elif perfil_ativo == "🛡️ Matriz de Riscos & Sanções (Art. 103)":
        st.title("🛡️ Matriz de Riscos e Garantias (Art. 103 / 96-102)")
        if not df_completo.empty:
            sel_r_contrato = st.selectbox("Selecione o Contrato:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()])
            id_r_sel = sel_r_contrato.split("ID: ")[-1].replace(")", "")

            with st.form("form_novo_risco"):
                rc1, rc2 = st.columns(2)
                with rc1:
                    ev_risco = st.text_input("Evento de Risco:", placeholder="Ex: Inadimplemento contratual")
                    prob = st.selectbox("Probabilidade:", ["Baixa", "Média", "Alta"])
                with rc2:
                    imp = st.selectbox("Impacto:", ["Baixo", "Médio", "Alto"])
                    mitig = st.text_area("Ação Mitigadora:")

                if perfil_usuario == "editor":
                    if st.form_submit_button("Adicionar à Matriz de Riscos"):
                        db_execute("""
                            INSERT INTO nllc_matriz_riscos (id_contrato, evento_risco, probabilidade, impacto, acao_mitigadora, responsavel)
                            VALUES (?, ?, ?, ?, ?, 'Contratada')
                        """, (id_r_sel, ev_risco, prob, imp, mitig))
                        st.success("Risco registrado!")
                        st.rerun()
                else:
                    st.info("🔒 Modo Somente Leitura.")

            df_matriz = db_query("SELECT * FROM nllc_matriz_riscos WHERE id_contrato = ?", params=(id_r_sel,))
            st.dataframe(df_matriz, use_container_width=True, hide_index=True)

    # 6. RAIO-X & AUDITORIA
    elif perfil_ativo == "🔍 Raio-X Integrado & Auditoria":
        st.title("🔍 Raio-X Integrado & Auditoria NLLC")
        if not df_completo.empty:
            sel_rx = st.selectbox("Escolha o Contrato:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()])
            id_rx = sel_rx.split("ID: ")[-1].replace(")", "")
            rx = df_completo[df_completo["id"] == id_rx].iloc[0]

            st.markdown(f"### Contrato nº `{rx['numero']}` — {rx['fornecedor']}")
            st.markdown(f"**Objeto:** {rx['objeto']}")

            st.divider()
            st.subheader("📑 Exportação Consolidada de Auditoria (Excel)")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_completo.to_excel(writer, index=False, sheet_name='Contratos_Governança_NLLC')
                db_query("SELECT * FROM nllc_matriz_riscos").to_excel(writer, index=False, sheet_name='Matriz_Riscos')
                db_query("SELECT * FROM nllc_ocorrencias_sancoes").to_excel(writer, index=False, sheet_name='Livro_Ocorrencias')
                db_query("SELECT * FROM nllc_medicoes_imr").to_excel(writer, index=False, sheet_name='Medicoes_SLA')

            st.download_button(
                label="📥 Baixar Relatório Completo de Auditoria (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"auditoria_nllc_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ==============================================================================
# DISPARADOR PRINCIPAL (OU LOGIN OU PAINEL)
# ==============================================================================
if not st.session_state["autenticado"]:
    render_tela_login()
else:
    render_painel_principal()
