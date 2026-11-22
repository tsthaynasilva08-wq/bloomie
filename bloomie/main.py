#inicio do trabalho: 8 de outubro

import tkinter as tk #importa as ferramentas usadas pra criar as telas
import sqlite3 #permite criar e acessar o banco de dados
import hashlib #usado pra proteger as senhas
import os #gera valores aleatórios usados na proteção das senhas
import hmac #ajuda na comparação segura das senhas
import secrets #gera códigos aleatórios e links seguros
from tkinter import messagebox, filedialog, ttk, simpledialog #messagebox mostra mensagens de aviso e confirmação pra o usuário
import shutil #copia a foto do perfil pra pasta do Bloomie, filedialog abre uma janela pra escolher arquivos no computador, ttk ajuda a criar listas de opções pra o usuário
import webbrowser #abre o link da aula online no navegador
from urllib.parse import urlsplit #verifica se o link da aula é válido
from PIL import Image, ImageTk, ImageDraw, ImageOps #importa as ferramentas pra abrir e mostrar as fotos no perfil
from banco_bloomie import BancoBloomie

PRECO_AULA_SEM_MATCH = 5 #sem curtida recíproca a aula custa 5 bloomcoins


PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__)) #pega a pasta onde tá o código pra achar o banco e as imagens


def carregar_fundo(nome, largura, altura):
    caminho = os.path.join(PASTA_PROJETO, nome)
    if not os.path.isfile(caminho):
        alternativa = os.path.join(PASTA_PROJETO, "fundo_bloomie_funcionalidades.gif")
        if not os.path.isfile(alternativa):
            raise FileNotFoundError(f"Imagem de fundo não encontrada: {caminho}")
        print(f"Fundo não encontrado: {nome}. Usando fundo alternativo.")
        caminho = alternativa
    with Image.open(caminho) as imagem:
        if imagem.size != (largura, altura):
            imagem = imagem.convert("RGBA").resize((largura, altura), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(imagem)
    return tk.PhotoImage(file=caminho)


def aplicar_fundo_funcionalidades(tela, largura, altura):
    imagem = carregar_fundo("fundo_bloomie_funcionalidades.gif", largura, altura)
    fundo = tk.Label(tela, image=imagem, bd=0, highlightthickness=0)
    fundo.image = imagem
    fundo.place(x=0, y=0, relwidth=1, relheight=1)
    fundo.lower()
    tela.fundo_funcionalidades = imagem
    return fundo

banco = BancoBloomie(PASTA_PROJETO) #faz a conexão com o banco
conexao = banco.conexao
cursor = banco.cursor #permite executar comandos no banco


def garantir_colunas_solicitacoes():
    cursor.execute("PRAGMA table_info(solicitacoes)")
    colunas = {linha[1] for linha in cursor.fetchall()}
    if not colunas:
        return

    campos = {
        "tipo": "TEXT DEFAULT 'paga'",
        "custo_bloomcoins": "INTEGER NOT NULL DEFAULT 5",
        "confirmado_aluno": "INTEGER DEFAULT 0",
        "confirmado_professor": "INTEGER DEFAULT 0",
        "data_aula": "TEXT",
        "hora_aula": "TEXT",
        "modalidade_aula": "TEXT",
        "local_aula": "TEXT",
        "situacao_agendamento": "TEXT NOT NULL DEFAULT 'sem_proposta'",
        "pedido_alteracao": "TEXT",
        "proposta_por": "INTEGER",
        "solicitado_por": "INTEGER"
    }
    faltando = [(nome, tipo) for nome, tipo in campos.items() if nome not in colunas]
    if not faltando:
        cursor.execute("UPDATE solicitacoes SET custo_bloomcoins = 0 WHERE tipo = 'troca' AND custo_bloomcoins != 0")
        cursor.execute("""
            UPDATE solicitacoes SET proposta_por = professor_id
            WHERE proposta_por IS NULL
              AND situacao_agendamento IN ('proposta', 'alteracao_solicitada', 'confirmado')
        """)
        conexao.commit()
        return

    destino_backup = os.path.join(PASTA_PROJETO, "bloomie_backup_antes_agendamento.db")
    if not os.path.isfile(destino_backup):
        conexao_backup = sqlite3.connect(destino_backup)
        try:
            conexao.backup(conexao_backup)
        finally:
            conexao_backup.close()

    for nome, tipo in faltando:
        cursor.execute(f"ALTER TABLE solicitacoes ADD COLUMN {nome} {tipo}")
    cursor.execute("UPDATE solicitacoes SET custo_bloomcoins = 0 WHERE tipo = 'troca'")
    if any(nome == "custo_bloomcoins" for nome, _ in faltando):
        #conserva o valor das aulas antigas de 20 moedas que já foram pagas
        cursor.execute("""
            UPDATE solicitacoes SET custo_bloomcoins = 20
            WHERE tipo = 'paga' AND status = 'concluida'
              AND EXISTS (
                  SELECT 1 FROM historico_bloomcoins mov
                  WHERE mov.usuario_id = solicitacoes.aluno_id
                    AND mov.quantidade = -20
                    AND mov.motivo = 'Aula #' || solicitacoes.id
              )
        """)
    cursor.execute("""
        UPDATE solicitacoes SET proposta_por = professor_id
        WHERE proposta_por IS NULL
          AND situacao_agendamento IN ('proposta', 'alteracao_solicitada', 'confirmado')
    """)
    conexao.commit()

garantir_colunas_solicitacoes()


#cria a tabela de usuários caso ela ainda não exista
#pra guardar se o usuario ficou conectado
#cria a tabela que guarda as informações do perfil
#cada usuário tem um saldo, que começa com 20 moedas
#guarda as missões que cada pessoa já terminou
#guarda de onde vieram as moedas
#guarda os pedidos de aulas entre os usuários
#guarda as curtidas e os perfis que a pessoa passou
banco.criar_tabelas()


def garantir_campos_recuperacao():
    #bancos antigos continuam funcionando sem depender de e-mail
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas = {linha[1] for linha in cursor.fetchall()}
    if "recuperacao_hash" not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN recuperacao_hash TEXT")
    if "frase_seguranca_hash" not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN frase_seguranca_hash TEXT")
    conexao.commit()


garantir_campos_recuperacao()
garantir_colunas_solicitacoes()

def tem_match_reciproco(usuario_a, usuario_b):
    if usuario_a == usuario_b:
        return False
    cursor.execute("""
        SELECT 1 FROM bloommatch_reacoes r
        JOIN habilidades h ON h.id = r.habilidade_id
        WHERE r.usuario_id = ? AND h.usuario_id = ? AND r.acao = 'curti'
        LIMIT 1
    """, (usuario_a, usuario_b))
    if cursor.fetchone() is None:
        return False
    cursor.execute("""
        SELECT 1 FROM bloommatch_reacoes r
        JOIN habilidades h ON h.id = r.habilidade_id
        WHERE r.usuario_id = ? AND h.usuario_id = ? AND r.acao = 'curti'
        LIMIT 1
    """, (usuario_b, usuario_a))
    return cursor.fetchone() is not None


def solicitar_aula(aluno_id, habilidade_id):
    cursor.execute("SELECT usuario_id FROM habilidades WHERE id = ?", (habilidade_id,))
    resultado = cursor.fetchone()
    if resultado is None:
        return "Habilidade não encontrada."
    professor_id = resultado[0]
    if aluno_id == professor_id:
        return "Você não pode solicitar sua própria habilidade."

    cursor.execute("""
        SELECT id FROM solicitacoes
        WHERE aluno_id = ? AND habilidade_id = ? AND status IN ('pendente', 'aceita')
    """, (aluno_id, habilidade_id))
    if cursor.fetchone():
        return "Você já tem uma solicitação aberta para essa habilidade."

    #um match recíproco permite troca gratuita, mas não é obrigatório pra pedir aula
    troca_direta = tem_match_reciproco(aluno_id, professor_id)
    tipo = "troca" if troca_direta else "paga"
    custo = 0 if troca_direta else PRECO_AULA_SEM_MATCH
    #as moedas são cobradas ao concluir, não na hora de enviar o pedido
    cursor.execute("""
        INSERT INTO solicitacoes
        (aluno_id, professor_id, habilidade_id, tipo, custo_bloomcoins, solicitado_por)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (aluno_id, professor_id, habilidade_id, tipo, custo, aluno_id))
    conexao.commit()
    if troca_direta:
        return "Solicitação de troca gratuita enviada! Aguarde a resposta."
    return f"Solicitação enviada! O professor pode aceitar. A aula custa {custo} BloomCoins, cobradas só após a conclusão confirmada pelos dois."


def enviar_solicitacao_de_aula(habilidade_id, parent, ao_atualizar=None):
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!", parent=parent)
        return False
    cursor.execute("""
        SELECT h.habilidade, h.usuario_id, u.nome
        FROM habilidades h JOIN usuarios u ON u.id = h.usuario_id
        WHERE h.id = ?
    """, (habilidade_id,))
    dados = cursor.fetchone()
    if not dados:
        messagebox.showwarning("Bloomie", "Essa habilidade não está mais disponível.", parent=parent)
        return False
    habilidade, professor_id, professor = dados
    gratuita = tem_match_reciproco(usuario_logado["id"], professor_id)
    valor = "troca gratuita pelo BloomMatch" if gratuita else f"aula por {PRECO_AULA_SEM_MATCH} BloomCoins"
    if not messagebox.askyesno(
        "Solicitar aula 🌸",
        f"Quer pedir a aula de {habilidade} com {professor}?\n\n"
        f"Tipo de aula: {valor}.\n"
        "O professor precisa aceitar e as moedas só serão transferidas "
        "depois que os dois confirmarem a aula.", parent=parent
    ):
        return False
    try:
        resposta = solicitar_aula(usuario_logado["id"], habilidade_id)
    except sqlite3.Error as erro:
        messagebox.showerror("Bloomie", f"Não foi possível solicitar a aula: {erro}", parent=parent)
        return False
    enviada = resposta.startswith("Solicitação enviada!") or resposta.startswith("Solicitação de troca gratuita enviada!")
    if enviada:
        messagebox.showinfo("Bloomie 🌸", resposta, parent=parent)
        if ao_atualizar:
            ao_atualizar()
    else:
        messagebox.showwarning("Bloomie", resposta, parent=parent)
    return enviada


def escolher_aula_com_pessoa(professor_id, parent, ao_atualizar=None):
    cursor.execute("SELECT nome FROM usuarios WHERE id = ?", (professor_id,))
    resultado = cursor.fetchone()
    if not resultado:
        messagebox.showinfo("Bloomie", "Esse perfil não está mais disponível.", parent=parent)
        return
    cursor.execute("""
        SELECT id, habilidade, categoria FROM habilidades
        WHERE usuario_id = ? ORDER BY habilidade COLLATE NOCASE
    """, (professor_id,))
    habilidades = cursor.fetchall()
    if not habilidades:
        messagebox.showinfo("Bloomie", "Essa pessoa ainda não compartilhou nenhuma habilidade.", parent=parent)
        return

    escolha = tk.Toplevel(parent)
    escolha.title("Bloomie - Pedir aula")
    escolha.geometry("540x430")
    escolha.resizable(False, False)
    escolha.transient(parent)
    escolha.lift(parent)
    escolha.focus_set()

    tela = tk.Canvas(escolha, width=540, height=430, bg="#FFF7F3", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 540, 430)
        escolha.fundo = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    tela.create_text(270, 42, text=f"Pedir aula com {resultado[0]} 🌸",
                     fill="#713D4D", font=("Arial", 19, "bold"), width=485, justify="center")
    valor = ("Troca gratuita (BloomMatch ♡)" if tem_match_reciproco(usuario_logado["id"], professor_id)
             else f"Sem match: {PRECO_AULA_SEM_MATCH} BloomCoins após a aula")
    tela.create_text(270, 82, text=valor, fill="#536B5C", font=("Arial", 11, "bold"))
    tela.create_text(270, 115, text="Escolha qual habilidade você quer aprender:",
                     fill="#594C50", font=("Arial", 11))

    fundo_campo(tela, 32, 138, 476, 185)
    lista = tk.Listbox(escolha, font=("Arial", 11), exportselection=False,
                       bg="#FFF7F3", fg="#713D4D", selectbackground="#D5A7B1",
                       relief="flat", highlightthickness=0)
    lista.place(x=46, y=150, width=448, height=160)
    for _, habilidade, categoria in habilidades:
        lista.insert("end", f"{habilidade}  ·  {categoria}")
    if habilidades:
        lista.selection_set(0)

    def confirmar_pedido():
        indice = lista.curselection()
        if not indice:
            messagebox.showwarning("Bloomie", "Escolha uma habilidade.", parent=escolha)
            return
        if enviar_solicitacao_de_aula(habilidades[indice[0]][0], escolha, ao_atualizar):
            escolha.destroy()

    tag_btn = "btn_confirmar_pedido"
    x, y, larg, alt, r = 170, 352, 200, 42, 21
    tela.create_oval(x, y, x + 2*r, y + alt, fill="#89998B", outline="", tags=tag_btn)
    tela.create_oval(x + larg - 2*r, y, x + larg, y + alt, fill="#89998B", outline="", tags=tag_btn)
    tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill="#89998B", outline="", tags=tag_btn)
    tela.create_text(x + larg/2, y + alt/2, text="Pedir aula", font=("Arial", 11, "bold"), fill="white", tags=tag_btn)
    tela.tag_bind(tag_btn, "<Button-1>", lambda e: confirmar_pedido())
    tela.tag_bind(tag_btn, "<Enter>", lambda e: tela.config(cursor="hand2"))
    tela.tag_bind(tag_btn, "<Leave>", lambda e: tela.config(cursor=""))


def oferecer_aula_para_pessoa(aluno_id, parent, ao_atualizar=None):
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!", parent=parent)
        return
    professor_id = usuario_logado["id"]
    if aluno_id == professor_id:
        messagebox.showinfo("Bloomie", "Você não pode oferecer aula para sua própria conta.", parent=parent)
        return
    cursor.execute("SELECT nome, usuario FROM usuarios WHERE id = ?", (aluno_id,))
    pessoa = cursor.fetchone()
    if not pessoa:
        messagebox.showwarning("Bloomie", "Esse perfil não está mais disponível.", parent=parent)
        return
    cursor.execute("""
        SELECT id, habilidade, categoria FROM habilidades
        WHERE usuario_id = ? ORDER BY habilidade COLLATE NOCASE
    """, (professor_id,))
    minhas = cursor.fetchall()
    if not minhas:
        messagebox.showinfo("Bloomie", "Compartilhe uma habilidade sua antes de oferecer uma aula.", parent=parent)
        return

    popup = tk.Toplevel(parent)
    popup.title("Bloomie - Oferecer aula")
    popup.geometry("575x485")
    popup.resizable(False, False)
    popup.transient(parent)
    popup.lift(parent)
    popup.focus_set()

    tela = tk.Canvas(popup, width=575, height=485, bg="#FFF7F3", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 575, 485)
        popup.fundo = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    tela.create_text(287, 45, text=f"Oferecer aula para {pessoa[0]} 🌸",
                     fill="#713D4D", font=("Arial", 19, "bold"), width=520, justify="center")
    tela.create_text(287, 84, text=f"Você está ensinando como @{usuario_logado['usuario']}.",
                     fill="#713D4D", font=("Arial", 10))
    custo = 0 if tem_match_reciproco(professor_id, aluno_id) else PRECO_AULA_SEM_MATCH
    tela.create_text(
        287, 118,
        text=("Troca gratuita pelo BloomMatch ♡" if custo == 0 else
              f"O aluno paga {custo} BloomCoins só depois da aula confirmada."),
        fill="#536B5C", font=("Arial", 11, "bold"), width=520, justify="center"
    )
    tela.create_text(38, 155, text="Escolha qual habilidade SUA você quer ensinar:",
                     fill="#594C50", font=("Arial", 11), anchor="nw")

    fundo_campo(tela, 36, 184, 502, 162)
    lista = tk.Listbox(popup, font=("Arial", 11), exportselection=False,
                       bg="#FFF7F3", fg="#713D4D", selectbackground="#D5A7B1",
                       relief="flat", highlightthickness=0, selectmode="browse")
    lista.place(x=50, y=195, width=474, height=140)
    for _, habilidade, categoria in minhas:
        lista.insert("end", f"{habilidade} · {categoria}")
    lista.selection_set(0)

    tela.create_text(287, 368, text="A oferta será enviada para o aluno aceitar ou recusar.",
                     fill="#713D4D", font=("Arial", 10))
    enviando = [False]

    def enviar_oferta():
        if enviando[0]:
            return
        escolha = lista.curselection()
        if not escolha:
            messagebox.showwarning("Bloomie", "Selecione uma habilidade sua.", parent=popup)
            return
        if usuario_logado is None or usuario_logado["id"] != professor_id:
            messagebox.showwarning("Bloomie", "A conta mudou. Abra a oferta novamente.", parent=popup)
            return
        habilidade_id = minhas[escolha[0]][0]
        enviando[0] = True
        try:
            cursor.execute("SELECT 1 FROM habilidades WHERE id = ? AND usuario_id = ?",
                           (habilidade_id, professor_id))
            if cursor.fetchone() is None:
                messagebox.showwarning("Bloomie", "A habilidade não pertence mais à sua conta.", parent=popup)
                return
            cursor.execute("""
                SELECT 1 FROM solicitacoes WHERE aluno_id = ? AND professor_id = ?
                  AND habilidade_id = ? AND status IN ('pendente', 'aceita')
            """, (aluno_id, professor_id, habilidade_id))
            if cursor.fetchone():
                messagebox.showinfo(
                    "Bloomie", "Já existe uma oferta ou aula ativa dessa habilidade com essa pessoa.", parent=popup
                )
                return
            cursor.execute("""
                INSERT INTO solicitacoes
                  (aluno_id, professor_id, habilidade_id, tipo, custo_bloomcoins, solicitado_por)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (aluno_id, professor_id, habilidade_id,
                  "troca" if custo == 0 else "paga", custo, professor_id))
            conexao.commit()
        except sqlite3.Error as erro:
            conexao.rollback()
            messagebox.showerror("Bloomie", f"Erro ao oferecer aula: {erro}", parent=popup)
            return
        finally:
            enviando[0] = False

        popup.destroy()
        messagebox.showinfo("Bloomie 🌸", "Oferta enviada!", parent=parent)
        if ao_atualizar:
            ao_atualizar()

    def criar_btn_canvas(x, y, larg, texto, cor, tag, cmd):
        alt, r = 42, 21
        tela.create_oval(x, y, x + 2*r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_oval(x + larg - 2*r, y, x + larg, y + alt, fill=cor, outline="", tags=tag)
        tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_text(x + larg/2, y + alt/2, text=texto, font=("Arial", 11, "bold"), fill="white", tags=tag)
        tela.tag_bind(tag, "<Button-1>", lambda e: cmd())
        tela.tag_bind(tag, "<Enter>", lambda e: tela.config(cursor="hand2"))
        tela.tag_bind(tag, "<Leave>", lambda e: tela.config(cursor=""))

    criar_btn_canvas(58, 412, 218, "Confirmar oferta", "#89998B", "btn_conf_oferta", enviar_oferta)
    criar_btn_canvas(339, 412, 170, "Cancelar", "#B98591", "btn_canc_oferta", popup.destroy)



def garantir_solicitacao_do_match(aluno_id, professor_id, habilidade_id, novo_evento=False):
    return banco.registrar_convite_match(aluno_id, professor_id, habilidade_id,
                                        novo_evento=novo_evento)


def sincronizar_matches_em_pedidos(usuario_id):
    return banco.sincronizar_matches_em_pedidos(usuario_id)


def registrar_curtida_bloommatch(usuario_id, habilidade_id, acao="curti"):
    #a mesma regra funciona no cartão e no botão curtir de volta
    if acao not in ("curti", "passei"):
        raise ValueError("Ação inválida")
    cursor.execute("SELECT usuario_id FROM habilidades WHERE id = ?", (habilidade_id,))
    dados = cursor.fetchone()
    if not dados or dados[0] == usuario_id:
        raise ValueError("Esta habilidade não está disponível para curtir.")
    dono_id = dados[0]
    cursor.execute("""
        SELECT acao FROM bloommatch_reacoes
        WHERE usuario_id = ? AND habilidade_id = ?
    """, (usuario_id, habilidade_id))
    anterior = cursor.fetchone()
    nova_curtida = acao == "curti" and (not anterior or anterior[0] != "curti")
    try:
        cursor.execute("""
            INSERT INTO bloommatch_reacoes (usuario_id, habilidade_id, acao)
            VALUES (?, ?, ?)
            ON CONFLICT(usuario_id, habilidade_id) DO UPDATE SET acao = excluded.acao
        """, (usuario_id, habilidade_id, acao))
        match = acao == "curti" and tem_match_reciproco(usuario_id, dono_id)
        criado = False
        if match:
            #o pedido e a curtida são confirmados na mesma transação
            criado = garantir_solicitacao_do_match(
                usuario_id, dono_id, habilidade_id, novo_evento=nova_curtida
            )
        conexao.commit()
        return match, criado, nova_curtida
    except sqlite3.Error:
        conexao.rollback()
        raise


def abrir_sala_online(pedido_id, parent, ao_atualizar=None):
    garantir_colunas_solicitacoes()
    if usuario_logado is None:
        return
    agendamento = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
    if not agendamento:
        messagebox.showwarning("Bloomie", "Essa aula não pertence à sua conta.", parent=parent)
        return
    if (agendamento["status"] != "aceita" or agendamento["modalidade_aula"] != "online"
            or agendamento["situacao_agendamento"] != "confirmado"):
        messagebox.showinfo("Bloomie", "A sala online fica disponível após a aceitação do pedido e a confirmação do horário online.", parent=parent)
        return
    cursor.execute("""
        SELECT COALESCE(a.nome, 'Aluno'), COALESCE(p.nome, 'Professor'),
               COALESCE(h.habilidade, 'Habilidade')
        FROM solicitacoes s
        LEFT JOIN usuarios a ON a.id = s.aluno_id
        LEFT JOIN usuarios p ON p.id = s.professor_id
        LEFT JOIN habilidades h ON h.id = s.habilidade_id
        WHERE s.id = ?
    """, (pedido_id,))
    aluno_nome, professor_nome, habilidade = cursor.fetchone()

    sala = tk.Toplevel(parent)
    sala.title("Bloomie - Sala de aula online")
    sala.geometry("980x730")
    sala.resizable(False, False)
    sala.transient(parent)

    tela = tk.Canvas(sala, width=980, height=730, bg="#FFF7F3", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 980, 730)
        sala.fundo_sala = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    def criar_btn(x, y, larg, texto, cor, tag, cmd):
        alt, r = 40, 20
        tela.create_oval(x, y, x + 2 * r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_oval(x + larg - 2 * r, y, x + larg, y + alt, fill=cor, outline="", tags=tag)
        tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_text(x + larg / 2, y + alt / 2, text=texto, font=("Arial", 10, "bold"), fill="white", tags=tag)
        tela.tag_bind(tag, "<Button-1>", lambda e: cmd())
        tela.tag_bind(tag, "<Enter>", lambda e: tela.config(cursor="hand2"))
        tela.tag_bind(tag, "<Leave>", lambda e: tela.config(cursor=""))

    tela.create_rectangle(0, 0, 980, 148, fill="#EFE0DE", outline="")
    tela.create_text(30, 18, text="sala de aula online ♡", fill="#713D4D", font=("Arial", 23, "bold"), anchor="nw")
    tela.create_text(32, 62, text=f"{habilidade}   •   {aluno_nome} + {professor_nome}",
                     fill="#594C50", font=("Arial", 12), anchor="nw")
    tela.create_text(32, 94, text=f"{agendamento['data_aula']} às {agendamento['hora_aula']}",
                     fill="#594C50", font=("Arial", 11), anchor="nw")

    def link_reuniao():
        atualizado = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
        salvo = (atualizado["local_aula"] or "").strip() if atualizado else ""
        if urlsplit(salvo).scheme == "https" and urlsplit(salvo).hostname:
            return salvo
        return f"https://jit.si{pedido_id}"

    def abrir_video():
        webbrowser.open(link_reuniao())

    def atualizar_botao_confirmacao():
        tela.delete("btn_conf_sala")
        dados = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
        if not dados or dados["status"] == "concluida":
            tela.create_text(945, 96, text="✓ Aula concluída", font=("Arial", 10, "bold"),
                             fill="#536B5C", anchor="e", tags="btn_conf_sala")
            return
        eh_prof = usuario_logado["id"] == dados["professor_id"]
        ja_confirmou = dados["confirmado_professor"] if eh_prof else dados["confirmado_aluno"]
        if ja_confirmou:
            tela.create_text(945, 96, text="✓ Você já confirmou esta aula", font=("Arial", 10, "bold"),
                             fill="#536B5C", anchor="e", tags="btn_conf_sala")
        else:
            texto_btn = "Marcar aula dada" if eh_prof else "Confirmar aula recebida"
            criar_btn(730, 82, 215, texto_btn, "#713D4D", "btn_conf_sala", confirmar_na_sala)

    def confirmar_na_sala():
        def apos_confirmar():
            atualizar_botao_confirmacao()
            if ao_atualizar:
                ao_atualizar()
        confirmar_conclusao_aula(pedido_id, sala, apos_confirmar)

    criar_btn(520, 28, 200, "↗ abrir videochamada", "#89998B", "btn_video_sala", abrir_video)
    criar_btn(730, 28, 215, "Voltar", "#B98591", "btn_voltar_sala", sala.destroy)
    atualizar_botao_confirmacao()

    tela.create_text(32, 165, text="mensagens da aula", fill="#713D4D", font=("Arial", 16, "bold"), anchor="nw")

    area = tk.Text(sala, bg="white", fg="#594C50", relief="flat",
                   borderwidth=0, font=("Arial", 11), wrap="word", padx=14, pady=12,
                   state="disabled")
    area.place(x=30, y=200, width=904, height=405)
    barra = ttk.Scrollbar(sala, orient="vertical", command=area.yview)
    barra.place(x=934, y=200, height=405)
    area.configure(yscrollcommand=barra.set)
    area.tag_configure("minha", foreground="#713D4D", font=("Arial", 11, "bold"))
    area.tag_configure("outra", foreground="#536B5C", font=("Arial", 11, "bold"))
    area.tag_configure("data", foreground="#837677", font=("Arial", 9))
    mensagens_anteriores = [None]

    def atualizar_mensagens(programar=True):
        if not sala.winfo_exists():
            return
        cursor.execute("""
            SELECT m.id, m.remetente_id, COALESCE(u.nome, 'Participante'),
                   m.mensagem, m.data_envio
            FROM sala_online_mensagens m
            LEFT JOIN usuarios u ON u.id = m.remetente_id
            WHERE m.pedido_id = ? ORDER BY m.id DESC LIMIT 100
        """, (pedido_id,))
        mensagens = cursor.fetchall()[::-1]
        if mensagens != mensagens_anteriores[0]:
            mensagens_anteriores[0] = mensagens
            area.configure(state="normal")
            area.delete("1.0", "end")
            if not mensagens:
                area.insert("end", "escreva uma mensagem para começar a conversar sobre a aula. 🌸\n")
            for _, remetente_id, nome, texto, data in mensagens:
                area.insert("end", nome + "  ", "minha" if remetente_id == usuario_logado["id"] else "outra")
                area.insert("end", str(data) + "\n", "data")
                area.insert("end", texto + "\n\n")
            area.configure(state="disabled")
            area.see("end")
        if programar:
            sala.after(3000, atualizar_mensagens)

    fundo_campo(tela, 30, 622, 775, 44)
    campo = tk.Entry(sala, bg="#FFF7F3", fg="#594C50", font=("Arial", 12), relief="flat", bd=0)
    campo.place(x=48, y=630, width=740, height=28)

    def enviar_mensagem(evento=None):
        texto = campo.get().strip()
        if not texto:
            return
        if len(texto) > 800:
            messagebox.showwarning("Bloomie", "Escreva até 800 caracteres por mensagem.", parent=sala)
            return
        cursor.execute("""
            INSERT INTO sala_online_mensagens (pedido_id, remetente_id, mensagem)
            SELECT id, ?, ? FROM solicitacoes
            WHERE id = ? AND status = 'aceita' AND modalidade_aula = 'online'
              AND situacao_agendamento = 'confirmado'
              AND (aluno_id = ? OR professor_id = ?)
        """, (usuario_logado["id"], texto, pedido_id, usuario_logado["id"], usuario_logado["id"]))
        if cursor.rowcount != 1:
            messagebox.showwarning("Bloomie", "A sala não está mais disponível para mensagens.", parent=sala)
            return
        conexao.commit()
        campo.delete(0, "end")
        atualizar_mensagens(False)

    criar_btn(820, 624, 130, "enviar ♡", "#89998B", "btn_env_msg", enviar_mensagem)
    campo.bind("<Return>", enviar_mensagem)

    tela.create_text(490, 695, text="não compartilhe informações pessoais na conversa.",
                     fill="#837677", font=("Arial", 9))
    atualizar_mensagens()

def responder_solicitacao(pedido_id, participante_id, aceitar):
    cursor.execute("""
        SELECT aluno_id, professor_id, status, tipo, custo_bloomcoins,
               COALESCE(solicitado_por, aluno_id)
        FROM solicitacoes WHERE id = ?
    """, (pedido_id,))
    pedido = cursor.fetchone()
    if not pedido or pedido[2] != "pendente":
        return "Essa solicitação não está mais pendente."
    aluno_id, professor_id, _, tipo, custo, quem_enviou = pedido
    if participante_id not in (aluno_id, professor_id) or participante_id == quem_enviou:
        return "Somente quem recebeu o pedido pode responder."
    #as moedas são cobradas só quando os dois confirmarem a conclusão
    #o aluno pode aceitar a oferta antes de juntar as 5 bloomcoins
    novo_status = "aceita" if aceitar else "recusada"
    cursor.execute("""
        UPDATE solicitacoes SET status = ?
        WHERE id = ? AND status = 'pendente'
    """, (novo_status, pedido_id))
    mudou = cursor.rowcount
    conexao.commit()
    if not mudou:
        return "Esse pedido já foi respondido. Atualize a lista."
    if aceitar and tipo == "paga" and consultar_saldo(aluno_id) < custo:
        return ("Solicitação aceita! Para concluir a aula, o aluno precisará "
                f"ter {custo} BloomCoins no saldo.")
    return "Solicitação aceita!" if aceitar else "Solicitação recusada."


def desistir_solicitacao(pedido_id, participante_id):
    cursor.execute("""
        SELECT aluno_id, professor_id, status, COALESCE(solicitado_por, aluno_id)
        FROM solicitacoes WHERE id = ?
    """, (pedido_id,))
    pedido = cursor.fetchone()
    if not pedido or participante_id not in pedido[:2]:
        return "Esse pedido não pertence à sua conta."
    if pedido[2] not in ("pendente", "aceita"):
        return "Esse pedido já foi finalizado."
    novo_status = "cancelada" if participante_id == pedido[3] else "recusada"
    cursor.execute("""
        UPDATE solicitacoes SET status = ?
        WHERE id = ? AND status IN ('pendente', 'aceita')
    """, (novo_status, pedido_id))
    alterou = cursor.rowcount
    conexao.commit()
    if not alterou:
        return "Esse pedido foi alterado. Atualize a lista."
    return "Aula recusada." if novo_status == "recusada" else "Solicitação cancelada."


def cancelar_solicitacao(pedido_id, aluno_id):
    cursor.execute("""
        UPDATE solicitacoes SET status = 'cancelada'
        WHERE id = ? AND aluno_id = ? AND status IN ('pendente', 'aceita')
    """, (pedido_id, aluno_id))
    alterou = cursor.rowcount
    conexao.commit()
    return "Solicitação cancelada." if alterou else "Não foi possível cancelar esse pedido."


def confirmar_aula(pedido_id, usuario_id):
    try:
        cursor.execute("BEGIN IMMEDIATE") #bloqueia mudanças enquanto confirma a aula
        cursor.execute("""
            SELECT aluno_id, professor_id, status, tipo,
                   confirmado_aluno, confirmado_professor, situacao_agendamento, custo_bloomcoins
            FROM solicitacoes WHERE id = ?
        """, (pedido_id,))
        pedido = cursor.fetchone()
        if not pedido or pedido[2] != "aceita":
            conexao.rollback()
            return "Essa aula não está aguardando confirmação."

        if pedido[6] != "confirmado":
            conexao.rollback()
            return "Antes de confirmar a aula, os dois precisam combinar o agendamento."

        aluno_id, professor_id, _, tipo, confirmou_aluno, confirmou_professor, _, custo = pedido
        if usuario_id not in (aluno_id, professor_id):
            conexao.rollback()
            return "Você não participa dessa aula."

        campo = "confirmado_aluno" if usuario_id == aluno_id else "confirmado_professor"
        cursor.execute(
            f"UPDATE solicitacoes SET {campo} = 1 WHERE id = ?",
            (pedido_id,)
        )
        confirmou_aluno = 1 if usuario_id == aluno_id else confirmou_aluno
        confirmou_professor = 1 if usuario_id == professor_id else confirmou_professor

        if not (confirmou_aluno and confirmou_professor):
            conexao.commit()
            return "Confirmação registrada! Falta a outra pessoa confirmar."

        if tipo == "paga":
            cursor.execute("""
                UPDATE bloomcoins SET saldo = saldo - ?
                WHERE usuario_id = ? AND saldo >= ?
            """, (custo, aluno_id, custo))
            if cursor.rowcount != 1:
                conexao.rollback()
                return "O aluno está sem moedas suficientes para concluir a aula."

            cursor.execute("""
                INSERT OR IGNORE INTO bloomcoins (usuario_id, saldo)
                VALUES (?, 20)
            """, (professor_id,))
            cursor.execute("""
                UPDATE bloomcoins SET saldo = saldo + ? WHERE usuario_id = ?
            """, (custo, professor_id))

            for pessoa, valor, motivo in (
                (aluno_id, -custo, f"Aula #{pedido_id}"),
                (professor_id, custo, f"Aula ensinada #{pedido_id}")
            ):
                cursor.execute("""
                    INSERT INTO historico_bloomcoins (usuario_id, quantidade, motivo)
                    VALUES (?, ?, ?)
                """, (pessoa, valor, motivo))

        cursor.execute("""
            UPDATE solicitacoes SET status = 'concluida' WHERE id = ?
        """, (pedido_id,))
        conexao.commit()
        return "Aula concluída!" + (f" As {custo} BloomCoins foram transferidas." if tipo == "paga" else " Troca direta concluída sem custo.")
    except sqlite3.Error:
        conexao.rollback() #desfaz as mudanças se o banco der erro
        raise


def responder_proposta_horario(pedido_id, parent, ao_atualizar, aceitar=True):
    #uma proposta só pode ser aprovada por quem não escolheu o horário
    if usuario_logado is None:
        return
    participante_id = usuario_logado["id"]
    agendamento = banco.consultar_agendamento(pedido_id, participante_id)
    if not agendamento or agendamento["status"] != "aceita":
        messagebox.showwarning("Bloomie", "Esse pedido não está disponível.", parent=parent)
        ao_atualizar()
        return
    if (agendamento["situacao_agendamento"] != "proposta"
            or agendamento["proposta_por"] == participante_id
            or agendamento["proposta_por"] is None):
        messagebox.showinfo("Bloomie", "Não há proposta de outra pessoa para responder.", parent=parent)
        ao_atualizar()
        return
    if aceitar:
        detalhes = (
            f"Data: {agendamento['data_aula']} às {agendamento['hora_aula']}\n"
            f"Modalidade: {agendamento['modalidade_aula']}\n"
            f"{'Endereço' if agendamento['modalidade_aula'] == 'presencial' else 'Link'}: "
            f"{agendamento['local_aula']}"
        )
        if not messagebox.askyesno(
            "Confirmar horário 🌸", "Você aceita essa proposta de aula?\n\n" + detalhes,
            parent=parent
        ):
            return
        mensagem = banco.aceitar_agendamento(pedido_id, participante_id)
    else:
        sugestao = simpledialog.askstring(
            "Pedir alteração", "O que você gostaria de mudar na data, no horário ou no local?",
            parent=parent
        )
        if sugestao is None:
            return
        mensagem = banco.pedir_alteracao_agendamento(pedido_id, participante_id, sugestao)
    if mensagem.startswith(("Horário confirmado", "Pedido de alteração enviado")):
        messagebox.showinfo("Bloomie 🌸", mensagem, parent=parent)
    else:
        messagebox.showwarning("Bloomie", mensagem, parent=parent)
    ao_atualizar()


def confirmar_conclusao_aula(pedido_id, parent, ao_atualizar):
    #dar aula e receber aula são confirmações diferentes; as duas concluem o pedido
    if usuario_logado is None:
        return
    dados = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
    if not dados or dados["status"] != "aceita" or dados["situacao_agendamento"] != "confirmado":
        messagebox.showwarning("Bloomie", "Combine e confirme o horário antes de concluir.", parent=parent)
        return
    professor = usuario_logado["id"] == dados["professor_id"]
    ja_confirmou = (dados["confirmado_professor"] if professor else dados["confirmado_aluno"])
    if ja_confirmou:
        messagebox.showinfo("Bloomie", "Você já confirmou. Falta a outra pessoa.", parent=parent)
        return
    pergunta = ("Você confirma que já deu essa aula?" if professor
                else "Você confirma que já recebeu essa aula?")
    if not messagebox.askyesno(
        "Concluir aula 🌸", pergunta + "\n\nAs moedas só serão transferidas depois das duas confirmações.",
        parent=parent
    ):
        return
    try:
        mensagem = confirmar_aula(pedido_id, usuario_logado["id"])
    except sqlite3.Error as erro:
        messagebox.showerror("Bloomie", f"Não foi possível confirmar a aula: {erro}", parent=parent)
        return
    if mensagem.startswith(("Aula concluída", "Confirmação registrada")):
        messagebox.showinfo("Bloomie 🌸", mensagem, parent=parent)
    else:
        messagebox.showwarning("Bloomie", mensagem, parent=parent)
    ao_atualizar()


def abrir_agendamento(pedido_id, parent, ao_atualizar):
    if usuario_logado is None:
        return

    agendamento = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
    if agendamento is None:
        messagebox.showwarning("Bloomie", "Solicitação não encontrada.", parent=parent)
        return

    agenda = tk.Toplevel(parent)
    agenda.title("Bloomie - Combinar aula")
    agenda.geometry("640x640")
    agenda.resizable(False, False)
    agenda.transient(parent)
    agenda.lift(parent)
    agenda.focus_set()

    tela = tk.Canvas(agenda, width=640, height=640, bg="#FFF7F3", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 640, 640)
        agenda.fundo_agenda = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    def criar_btn(x, y, larg, texto, cor, tag, cmd):
        alt, r = 42, 21
        tela.create_oval(x, y, x + 2 * r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_oval(x + larg - 2 * r, y, x + larg, y + alt, fill=cor, outline="", tags=tag)
        tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_text(x + larg / 2, y + alt / 2, text=texto, font=("Arial", 11, "bold"), fill="white", tags=tag)
        tela.tag_bind(tag, "<Button-1>", lambda e: cmd())
        tela.tag_bind(tag, "<Enter>", lambda e: tela.config(cursor="hand2"))
        tela.tag_bind(tag, "<Leave>", lambda e: tela.config(cursor=""))

    tela.create_text(320, 38, text="Combinar aula 🌸", font=("Arial", 21, "bold"), fill="#713D4D")

    participante_id = usuario_logado["id"]
    quem_propos = agendamento.get("proposta_por")
    if agendamento["status"] != "aceita":
        tela.create_text(320, 120, text="O pedido precisa ser aceito antes de combinar a aula.",
                         fill="#713D4D", font=("Arial", 11))
        criar_btn(225, 575, 190, "Fechar", "#B98591", "btn_fechar_ag", agenda.destroy)
        return

    situacao = agendamento["situacao_agendamento"] or "sem_proposta"
    modalidade_atual_str = (agendamento["modalidade_aula"] or "a definir").capitalize()
    local_str = (
        f"Endereço: {agendamento['local_aula'] or 'a definir'}"
        if agendamento["modalidade_aula"] == "presencial"
        else "Local: Sala de aula online do Bloomie"
    )
    detalhes = (
        f"Data: {agendamento['data_aula'] or 'a definir'}\n"
        f"Horário: {agendamento['hora_aula'] or 'a definir'}\n"
        f"Modalidade: {modalidade_atual_str}\n"
        f"{local_str}"
    )

    tela.create_rectangle(50, 72, 590, 178, fill="#F8E9E6", outline="#D5B8B1", width=1)
    tela.create_text(68, 86, text=detalhes, font=("Arial", 11), fill="#594C50", anchor="nw", width=500)

    if situacao == "confirmado":
        tela.create_text(
            320, 205,
            text="✓ aula agendada! depois da aula, os dois devem confirmar a conclusão.",
            font=("Arial", 11, "bold"), fill="#536B5C", width=540, justify="center"
        )
        if agendamento["modalidade_aula"] == "online":
            criar_btn(200, 245, 240, "♡ Entrar na sala online", "#89998B", "btn_sala_ag",
                      lambda: abrir_sala_online(pedido_id, agenda, ao_atualizar))
    elif situacao == "alteracao_solicitada":
        texto_alteracao = agendamento["pedido_alteracao"] or "A outra pessoa pediu um ajuste no horário."
        mensagem_alteracao = (
            "a outra pessoa pediu uma alteração: " + texto_alteracao
            if participante_id == quem_propos else
            "seu pedido de alteração foi enviado. aguarde a outra pessoa sugerir um novo horário."
        )
        tela.create_text(320, 205, text=mensagem_alteracao, font=("Arial", 11), fill="#713D4D", width=540, justify="center")
    elif situacao == "proposta":
        msg = ("proposta enviada! aguardando a outra pessoa responder."
               if participante_id == quem_propos
               else "a outra pessoa sugeriu esta aula. aceite o horário ou peça alteração.")
        tela.create_text(320, 205, text=msg, font=("Arial", 11), fill="#713D4D", width=540, justify="center")
    else:
        tela.create_text(320, 205, text="ainda não há proposta. você pode sugerir o horário da aula.",
                         font=("Arial", 11), fill="#713D4D")

    def terminar(mensagem):
        messagebox.showinfo("Bloomie 🌸", mensagem, parent=agenda)
        ao_atualizar()
        agenda.destroy()

    if (situacao == "sem_proposta"
            or (situacao == "alteracao_solicitada" and participante_id == quem_propos)
            or (situacao == "proposta" and participante_id == quem_propos)):

        tela.create_text(52, 232, text="data (DD/MM/AAAA) · digite só os números",
                         font=("Arial", 10, "bold"), fill="#713D4D", anchor="nw")
        fundo_campo(tela, 50, 253, 540, 36)
        campo_data = tk.Entry(agenda, font=("Arial", 11), bg="#FFF7F3", fg="#594C50", relief="flat", bd=0)
        campo_data.place(x=66, y=258, width=508, height=26)
        campo_data.insert(0, agendamento["data_aula"] or "")
        formatar_entrada_data_hora(campo_data, "data")

        tela.create_text(52, 300, text="horário (HH:MM) · digite só os números",
                         font=("Arial", 10, "bold"), fill="#713D4D", anchor="nw")
        fundo_campo(tela, 50, 321, 540, 36)
        campo_hora = tk.Entry(agenda, font=("Arial", 11), bg="#FFF7F3", fg="#594C50", relief="flat", bd=0)
        campo_hora.place(x=66, y=326, width=508, height=26)
        campo_hora.insert(0, agendamento["hora_aula"] or "")
        formatar_entrada_data_hora(campo_hora, "hora")

        tela.create_text(52, 368, text="modalidade", font=("Arial", 10, "bold"), fill="#713D4D", anchor="nw")
        escolha = tk.StringVar(value=agendamento["modalidade_aula"] or "online")
        menu_modalidade = tk.OptionMenu(agenda, escolha, "online", "presencial")
        menu_modalidade.config(
            bg="#89998B", fg="white", activebackground="#718575",
            activeforeground="white", highlightthickness=0, bd=0,
            relief="flat", font=("Arial", 10, "bold")
        )
        menu_modalidade["menu"].config(
            bg="#FFF7F3", fg="#713D4D", activebackground="#F0DDE0",
            activeforeground="#713D4D", bd=0, relief="flat"
        )
        menu_modalidade.place(x=50, y=389, width=140, height=32)

        rotulo_local = tela.create_text(52, 434, text="", font=("Arial", 10, "bold"), fill="#713D4D", anchor="nw")
        aviso_online = tela.create_text(
            52, 460,
            text="🌸 A aula acontecerá na Sala Online do Bloomie, liberada assim que o horário for confirmado.",
            font=("Arial", 10), fill="#536B5C", anchor="nw", width=535
        )
        campo_local = tk.Entry(agenda, font=("Arial", 11), bg="#FFF7F3", fg="#594C50", relief="flat", bd=0)
        if agendamento["modalidade_aula"] == "presencial":
            campo_local.insert(0, agendamento["local_aula"] or "")

        def atualizar_campo_local(*args):
            tela.delete("fundo_local")
            if escolha.get() == "presencial":
                tela.itemconfigure(aviso_online, state="hidden")
                tela.itemconfig(rotulo_local, text="endereço da aula (rua, número, bairro, cidade)")
                raio = 16
                x, y, largura, altura = 50, 455, 540, 36
                tela.create_oval(x, y, x + 2 * raio, y + altura, fill="#D5B8B1", outline="", tags="fundo_local")
                tela.create_oval(x + largura - 2 * raio, y, x + largura, y + altura, fill="#D5B8B1", outline="", tags="fundo_local")
                tela.create_rectangle(x + raio, y, x + largura - raio, y + altura, fill="#D5B8B1", outline="", tags="fundo_local")
                tela.create_oval(x + 2, y + 2, x + 2 + 2 * raio, y + altura - 2, fill="#FFF7F3", outline="", tags="fundo_local")
                tela.create_oval(x + largura - 2 - 2 * raio, y + 2, x + largura - 2, y + altura - 2, fill="#FFF7F3", outline="", tags="fundo_local")
                tela.create_rectangle(x + 2 + raio, y + 2, x + largura - 2 - raio, y + altura - 2, fill="#FFF7F3", outline="", tags="fundo_local")
                campo_local.place(x=66, y=460, width=508, height=26)
            else:
                campo_local.place_forget()
                tela.itemconfig(rotulo_local, text="ambiente da aula")
                tela.itemconfigure(aviso_online, state="normal")

        escolha.trace_add("write", atualizar_campo_local)
        atualizar_campo_local()

        def enviar_proposta():
            if len(campo_data.get()) != 10:
                messagebox.showwarning("Bloomie", "Complete a data com dia, mês e ano (DD/MM/AAAA).", parent=agenda)
                campo_data.focus_set()
                return
            if len(campo_hora.get()) != 5:
                messagebox.showwarning("Bloomie", "Complete o horário com horas e minutos (HH:MM).", parent=agenda)
                campo_hora.focus_set()
                return
            local_envio = campo_local.get().strip() if escolha.get() == "presencial" else ""
            mensagem = banco.propor_agendamento(
                pedido_id, usuario_logado["id"], campo_data.get(),
                campo_hora.get(), escolha.get(), local_envio
            )
            if mensagem.startswith("Proposta enviada"):
                terminar(mensagem)
            else:
                messagebox.showwarning("Bloomie", mensagem, parent=agenda)

        campo_data.bind("<Return>", lambda e: (campo_hora.focus_set(), "break"), add="+")
        campo_hora.bind("<Return>", lambda e: (menu_modalidade.focus_set(), "break"), add="+")
        campo_local.bind("<Return>", lambda e: (enviar_proposta(), "break"), add="+")
        campo_data.focus_set()

        criar_btn(215, 515, 210, "Enviar proposta", "#B98591", "btn_env_prop", enviar_proposta)

    elif situacao == "proposta" and participante_id != quem_propos:

            criar_btn(215, 515, 210, "Enviar proposta", "#B98591", "btn_env_prop", enviar_proposta)

    elif situacao == "proposta" and participante_id != quem_propos:
        def responder_na_janela(aceitar):
            anterior = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
            responder_proposta_horario(pedido_id, agenda, ao_atualizar, aceitar)
            atual = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
            if (anterior and atual and anterior["situacao_agendamento"] != atual["situacao_agendamento"]):
                agenda.destroy()

        criar_btn(125, 260, 185, "Aceitar horário", "#89998B", "btn_ac_hor", lambda: responder_na_janela(True))
        criar_btn(330, 260, 185, "Pedir alteração", "#B98591", "btn_alt_hor", lambda: responder_na_janela(False))

    criar_btn(245, 575, 150, "Voltar", "#B98591", "btn_voltar_ag", agenda.destroy)


def combinar_pedido_ou_aceitar(pedido_id, parent, ao_atualizar):
    garantir_colunas_solicitacoes()
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!", parent=parent)
        return

    try:
        agendamento = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
        if agendamento is None:
            messagebox.showwarning("Bloomie", "Não encontrei essa solicitação. Atualize a lista.", parent=parent)
            return

        status = agendamento["status"]
        if status == "pendente":
            if agendamento["solicitado_por"] == usuario_logado["id"]:
                messagebox.showinfo(
                    "Bloomie", "O pedido foi enviado e está aguardando a outra pessoa aceitar. "
                    "Assim que ela aceitar, vocês poderão combinar a aula.", parent=parent
                )
                return
            aceitar = messagebox.askyesno(
                "Bloomie 🌸", "Você recebeu este pedido de aula. "
                "Quer aceitar agora e abrir o agendamento?", parent=parent
            )
            if not aceitar:
                return
            resposta = responder_solicitacao(pedido_id, usuario_logado["id"], True)
            #a oferta pode ser aceita mesmo antes do aluno juntar as moedas
            if not resposta.startswith("Solicitação aceita!"):
                messagebox.showwarning("Bloomie", resposta, parent=parent)
                ao_atualizar()
                return
            ao_atualizar()
            messagebox.showinfo("Bloomie 🌸", "Pedido aceito! Agora escolha os detalhes da aula.", parent=parent)
        elif status != "aceita":
            avisos = {
                "concluida": "Essa aula já foi concluída.",
                "recusada": "Essa solicitação foi recusada.",
                "cancelada": "Essa solicitação foi cancelada."
            }
            messagebox.showinfo("Bloomie", avisos.get(status, "Esse pedido não pode ser agendado."), parent=parent)
            return

        abrir_agendamento(pedido_id, parent, ao_atualizar)
    except (sqlite3.Error, tk.TclError, ValueError) as erro:
        messagebox.showerror("Bloomie", f"Não foi possível abrir a aula: {erro}", parent=parent)



def ver_detalhes_aula_concluida(pedido_id, parent):
    #pedido concluído pode ser consultado, mas não agendado de novo
    if usuario_logado is None:
        return
    dados = banco.consultar_agendamento(pedido_id, usuario_logado["id"])
    if not dados or dados["status"] != "concluida":
        messagebox.showinfo("Bloomie", "Essa aula não está mais no histórico de concluídas.", parent=parent)
        return
    cursor.execute("""
        SELECT h.habilidade, s.tipo, s.custo_bloomcoins,
               COALESCE(u.nome, 'Participante')
        FROM solicitacoes s
        LEFT JOIN habilidades h ON h.id = s.habilidade_id
        LEFT JOIN usuarios u ON u.id = CASE
            WHEN s.professor_id = ? THEN s.aluno_id ELSE s.professor_id END
        WHERE s.id = ?
    """, (usuario_logado["id"], pedido_id))
    registro = cursor.fetchone()
    habilidade, tipo, custo, pessoa = registro if registro else ("Habilidade removida", "paga", 5, "Participante")
    descricao = (
        f"Aula #{pedido_id} • {habilidade or 'Habilidade removida'}\n"
        f"Com: {pessoa}\n"
        f"Data: {dados['data_aula'] or 'não informada'}\n"
        f"Horário: {dados['hora_aula'] or 'não informado'}\n"
        f"Modalidade: {dados['modalidade_aula'] or 'não informada'}\n"
        f"{'Endereço' if dados['modalidade_aula'] == 'presencial' else 'Link da aula'}: "
        f"{dados['local_aula'] or 'não informado'}\n"
        f"Custo: {'troca gratuita' if tipo == 'troca' else str(custo) + ' BloomCoins'}\n"
        "Situação: concluída. Para outra aula, faça um novo pedido."
    )
    messagebox.showinfo("Bloomie - Detalhes da aula", descricao, parent=parent)


def pedir_nova_aula_de_pedido(pedido_id, parent, ao_atualizar=None):
    #uma aula nova gera outra solicitação, preservando o histórico antigo
    if usuario_logado is None:
        return
    cursor.execute("SELECT aluno_id, professor_id, status FROM solicitacoes WHERE id = ?", (pedido_id,))
    registro = cursor.fetchone()
    if not registro or registro[2] != "concluida":
        messagebox.showwarning("Bloomie", "Selecione uma aula concluída.", parent=parent)
        return
    aluno_id, professor_id, _ = registro
    if usuario_logado["id"] == aluno_id:
        escolher_aula_com_pessoa(professor_id, parent, ao_atualizar)
    elif usuario_logado["id"] == professor_id:
        oferecer_aula_para_pessoa(aluno_id, parent, ao_atualizar)
    else:
        messagebox.showwarning("Bloomie", "Essa aula não pertence à sua conta.", parent=parent)


def listar_curtidas_sem_reciprocidade(usuario_id):
    return [pessoa for pessoa in consultar_curtidas_recebidas(usuario_id) if not pessoa[4]]


def abrir_curtir_de_volta_solicitacoes(parent, ao_atualizar=None):
    #abre direto as curtidas pendentes, sem precisar ir até o BloomMatch
    if usuario_logado is None:
        return
    pendentes = listar_curtidas_sem_reciprocidade(usuario_logado["id"])
    if not pendentes:
        messagebox.showinfo("Bloomie", "Não há curtidas aguardando resposta.", parent=parent)
        if ao_atualizar:
            ao_atualizar()
        return
    popup = tk.Toplevel(parent)
    popup.title("Bloomie - Curtir de volta")
    popup.geometry("640x555")
    popup.resizable(False, False)
    popup.configure(bg="#FFF7F3")
    aplicar_fundo_funcionalidades(popup, 640, 555)
    popup.transient(parent)
    tk.Label(popup, text="♡ Curtir de volta", font=("Arial", 22, "bold"),
             fg="#713D4D", bg="#FFF7F3").pack(pady=(20, 8))
    tk.Label(popup, text="Escolha a pessoa que curtiu sua habilidade:",
             font=("Arial", 11), fg="#594C50", bg="#FFF7F3").pack()
    lista = tk.Listbox(popup, font=("Arial", 11), bg="white", fg="#713D4D",
                       selectbackground="#D5A7B1", relief="flat", exportselection=False,
                       height=5)
    lista.pack(fill="x", padx=35, pady=(12, 14))
    pessoas = []
    for pessoa in pendentes:
        pessoa_id, nome, usuario, habilidades, _ = pessoa
        pessoas.append(pessoa)
        lista.insert("end", f"{nome} (@{usuario}) • curtiu: {habilidades or 'sua habilidade'}")
    if pessoas:
        lista.selection_set(0)
    tk.Label(popup, text="Escolha uma habilidade dessa pessoa para retribuir:",
             font=("Arial", 11), fg="#594C50", bg="#FFF7F3").pack()
    lista_habilidades = tk.Listbox(popup, font=("Arial", 11), bg="white", fg="#713D4D",
                                  selectbackground="#D5A7B1", relief="flat", exportselection=False,
                                  height=6)
    lista_habilidades.pack(fill="x", padx=35, pady=(10, 14))
    habilidades_da_pessoa = []

    def mostrar_habilidades(evento=None):
        nonlocal habilidades_da_pessoa
        lista_habilidades.delete(0, "end")
        selecionados = lista.curselection()
        habilidades_da_pessoa = []
        if not selecionados:
            return
        pessoa_id = pessoas[selecionados[0]][0]
        cursor.execute("""
            SELECT id, habilidade, categoria FROM habilidades
            WHERE usuario_id = ? ORDER BY habilidade COLLATE NOCASE
        """, (pessoa_id,))
        habilidades_da_pessoa = cursor.fetchall()
        for _, nome, categoria in habilidades_da_pessoa:
            lista_habilidades.insert("end", f"{nome} • {categoria}")
        if habilidades_da_pessoa:
            lista_habilidades.selection_set(0)

    def confirmar():
        pessoa_selecionada, habilidade_selecionada = lista.curselection(), lista_habilidades.curselection()
        if not pessoa_selecionada:
            messagebox.showwarning("Bloomie", "Escolha uma pessoa primeiro.", parent=popup)
            return
        if not habilidades_da_pessoa:
            messagebox.showinfo(
                "Bloomie", "Essa pessoa ainda não publicou nenhuma habilidade para você curtir. "
                "Ela precisa compartilhar uma habilidade primeiro. Vocês ainda podem combinar uma aula sem match.",
                parent=popup
            )
            return
        if not habilidade_selecionada:
            messagebox.showwarning("Bloomie", "Escolha a habilidade que deseja curtir.", parent=popup)
            return
        pessoa_id = pessoas[pessoa_selecionada[0]][0]
        habilidade_id = habilidades_da_pessoa[habilidade_selecionada[0]][0]
        usuario_id = usuario_logado["id"]
        #confere se a curtida e a habilidade ainda existem antes de salvar
        cursor.execute("""
            SELECT 1 FROM bloommatch_reacoes r
            JOIN habilidades h ON h.id = r.habilidade_id
            WHERE r.usuario_id = ? AND h.usuario_id = ? AND r.acao = 'curti' LIMIT 1
        """, (pessoa_id, usuario_id))
        if cursor.fetchone() is None:
            messagebox.showwarning("Bloomie", "A curtida já não está disponível.", parent=popup)
            return
        cursor.execute("SELECT 1 FROM habilidades WHERE id = ? AND usuario_id = ?",
                       (habilidade_id, pessoa_id))
        if cursor.fetchone() is None:
            messagebox.showwarning("Bloomie", "A habilidade não está mais disponível.", parent=popup)
            return
        try:
            combinou, gerou_pedido, _ = registrar_curtida_bloommatch(usuario_id, habilidade_id)
        except (sqlite3.Error, ValueError) as erro:
            messagebox.showerror("Bloomie", f"Não foi possível curtir: {erro}", parent=popup)
            return
        messagebox.showinfo("Bloomie ♡", "Curtida retribuída! " +
                            ("Convite de troca enviado." if gerou_pedido else
                             "Vocês deram match. Confira suas solicitações."), parent=popup)
        popup.destroy()
        if ao_atualizar:
            ao_atualizar()

    lista.bind("<<ListboxSelect>>", mostrar_habilidades)
    mostrar_habilidades()
    botoes = tk.Frame(popup, bg="#FFF7F3")
    botoes.pack(pady=(3, 20))
    botao_suave(botoes, "♡ Curtir", confirmar, largura=195, cor="#89998B").pack(side="left", padx=12)
    botao_suave(botoes, "Voltar", popup.destroy, largura=165).pack(side="left", padx=12)


def abrir_solicitacoes():
    garantir_colunas_solicitacoes()
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return
    sincronizar_matches_em_pedidos(usuario_logado["id"])

    pedidos = tk.Toplevel(janela)
    pedidos.title("Bloomie - Minhas Solicitações (versão corrigida)")
    pedidos.geometry("1300x800")
    pedidos.resizable(False, False)
    tela = tk.Canvas(pedidos, width=1300, height=800, bg="#F8E8F0", highlightthickness=0)
    tela.pack()

    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fundo_bloomie_funcionalidades.gif")
    try:
        imagem = tk.PhotoImage(file=caminho)
        pedidos.fundo = imagem
        tela.create_image(0, 0, image=imagem, anchor="nw")
    except (tk.TclError, OSError) as erro:
        print("Não foi possível carregar o fundo:", erro)

    tela.create_text(315, 65, text="Minhas Solicitações 🌸", anchor="nw",
                     font=("Arial", 26, "bold"), fill="#713D4D")
    tela.create_text(315, 116, text="Receba pedidos, aceite aulas e combine horários.",
                     anchor="nw", font=("Arial", 12), fill="#594C50")

    aviso = tela.create_text(
        315, 148, text="", font=("Arial", 11),
        fill="#713D4D", anchor="nw", width=885
    )

    estilo = ttk.Style(pedidos)
    estilo.configure("Bloomie.Treeview", font=("Arial", 11), rowheight=37,
                     background="#FFF7F3", fieldbackground="#FFF7F3",
                     foreground="#594C50", borderwidth=0, relief="flat")
    estilo.configure("Bloomie.Treeview.Heading", font=("Arial", 11, "bold"),
                     background="#E9D8D3", foreground="#713D4D",
                     relief="flat", borderwidth=0)
    estilo.map("Bloomie.Treeview", background=[("selected", "#DABDC2")],
               foreground=[("selected", "#713D4D")])

    colunas = ("numero", "direcao", "pessoa", "habilidade", "tipo", "status")
    tabela = ttk.Treeview(pedidos, columns=colunas, show="headings",
                          selectmode="browse", style="Bloomie.Treeview", height=10)
    for campo, titulo, tamanho in (
        ("numero", "Pedido", 70),
        ("direcao", "Origem", 100),
        ("pessoa", "Pessoa", 175),
        ("habilidade", "Habilidade", 197),
        ("tipo", "Modalidade", 120),
        ("status", "Situação", 248)
    ):
        tabela.heading(campo, text=titulo)
        tabela.column(campo, width=tamanho, anchor="center", stretch=False)
    tabela.place(x=315, y=225, width=920, height=390)

    aba = tk.StringVar(value="todos")
    dados_linhas = {}

    def _atualizar_dados():
        selecionados = tabela.selection()
        for item in tabela.get_children():
            tabela.delete(item)
        dados_linhas.clear()
        usuario_id = usuario_logado["id"]
        modo = aba.get()
        sincronizar_matches_em_pedidos(usuario_id)

        cursor.execute("""
            SELECT status, COUNT(*) FROM solicitacoes
            WHERE aluno_id = ? OR professor_id = ?
            GROUP BY status
        """, (usuario_id, usuario_id))
        totais_status = dict(cursor.fetchall())
        total_conta = sum(totais_status.values())
        pendentes = totais_status.get("pendente", 0)
        aceitos = totais_status.get("aceita", 0)

        if modo == "matches":
            matches = listar_matches_para_agendamento(usuario_id)
            curtidas_recebidas = consultar_curtidas_recebidas(usuario_id)
            for pessoa_id, nome, usuario, habilidades, habilidade_id in matches:
                cursor.execute("""
                    SELECT s.id, s.status, COALESCE(s.solicitado_por, s.aluno_id)
                    FROM solicitacoes s
                    WHERE (s.aluno_id = ? AND s.professor_id = ?)
                       OR (s.aluno_id = ? AND s.professor_id = ?)
                    ORDER BY CASE s.status WHEN 'pendente' THEN 0 WHEN 'aceita' THEN 1 ELSE 2 END,
                             s.id DESC LIMIT 1
                """, (usuario_id, pessoa_id, pessoa_id, usuario_id))
                pedido_match = cursor.fetchone()
                chave = f"match-{pessoa_id}"
                if pedido_match:
                    numero, status, remetente_id = pedido_match
                    recebido = remetente_id != usuario_id
                    dados_linhas[chave] = ("pedido", numero, status, recebido)
                    situacao = ("Aceite o pedido" if recebido else "Aguardando resposta") if status == "pendente" else status.capitalize()
                    origem = "Recebido" if recebido else "Enviado"
                else:
                    numero = "—"
                    origem = "BloomMatch"
                    situacao = "Curtida recíproca (sem pedido)"
                    dados_linhas[chave] = ("match", pessoa_id, "sem_pedido", False, habilidade_id)
                tabela.insert("", "end", iid=chave, values=(
                    numero, origem, f"{nome} (@{usuario})",
                    habilidades or "Habilidade disponível", "Troca grátis", situacao
                ))
            existentes = {pessoa_id for pessoa_id, *_ in matches}
            for pessoa_id, nome, usuario, habilidades, reciproco in curtidas_recebidas:
                if pessoa_id in existentes:
                    continue
                chave = f"curtida-{pessoa_id}"
                if reciproco:
                    dados_linhas[chave] = ("match", pessoa_id, "sem_pedido", False, None)
                    status_curtida = "BloomMatch ♡ (pedido não encontrado)"
                else:
                    dados_linhas[chave] = ("curtida", pessoa_id, "aguardando", False)
                    status_curtida = "Curtiu você ♡ (aguarda retribuição)"
                tabela.insert("", "end", iid=chave, values=(
                    "—", "BloomMatch" if reciproco else "Curtida",
                    f"{nome} (@{usuario})", habilidades or "Habilidade disponível",
                    "Troca grátis" if reciproco else "5 moedas", status_curtida
                ))
            tela.itemconfig(texto_aba, text=f"BloomMatches e curtidas ({len(tabela.get_children())})")
            if matches or curtidas_recebidas:
                tela.itemconfig(aviso, text=(
                    "Curtidas recíprocas geram trocas gratuitas. Sem match também dá pra pedir "
                    "uma aula por 5 bloomcoins."
                ))
            else:
                tela.itemconfig(aviso, text=(
                    f"Nenhum BloomMatch encontrado para @{usuario_logado['usuario']}."
                ))
        else:
            if modo == "recebidos":
                filtro = "(s.aluno_id = ? OR s.professor_id = ?) AND COALESCE(s.solicitado_por, s.aluno_id) != ?"
                parametros = (usuario_id, usuario_id, usuario_id)
            elif modo == "enviados":
                filtro = "(s.aluno_id = ? OR s.professor_id = ?) AND COALESCE(s.solicitado_por, s.aluno_id) = ?"
                parametros = (usuario_id, usuario_id, usuario_id)
            else:
                filtro = "(s.aluno_id = ? OR s.professor_id = ?)"
                parametros = (usuario_id, usuario_id)
            cursor.execute(f"""
                SELECT s.id, COALESCE(u.nome, 'Conta indisponível'),
                       h.habilidade, s.tipo, s.status,
                       s.confirmado_aluno, s.confirmado_professor, s.custo_bloomcoins,
                       COALESCE(s.situacao_agendamento, 'sem_proposta'),
                       s.professor_id, COALESCE(s.solicitado_por, s.aluno_id)
                FROM solicitacoes s
                LEFT JOIN usuarios u ON u.id = CASE
                    WHEN s.professor_id = ? THEN s.aluno_id ELSE s.professor_id END
                LEFT JOIN habilidades h ON h.id = s.habilidade_id
                WHERE {filtro} AND h.id IS NOT NULL
                ORDER BY CASE s.status
                    WHEN 'pendente' THEN 0 WHEN 'aceita' THEN 1
                    WHEN 'concluida' THEN 2 ELSE 3 END, s.id DESC
            """, (usuario_id, *parametros))
            registros = cursor.fetchall()
            for numero, nome, habilidade, tipo, status, conf_aluno, conf_professor, custo, situacao_agenda, professor_id, remetente_id in registros:
                recebido = remetente_id != usuario_id
                dados_linhas[str(numero)] = ("pedido", numero, status, recebido)
                if status == "pendente":
                    status_texto = (
                        "Oferta recebida — aceite ou recuse"
                        if recebido and professor_id == remetente_id else
                        "Pedido recebido — aceite ou recuse" if recebido else
                        "Oferta enviada — aguardando aluno" if professor_id == remetente_id else
                        "Aguardando resposta"
                    )
                elif status == "aceita":
                    marcou = conf_professor if professor_id == usuario_id else conf_aluno
                    if marcou:
                        status_texto = "Aguardando confirmação da outra pessoa"
                    elif situacao_agenda == "proposta":
                        cursor.execute("SELECT proposta_por FROM solicitacoes WHERE id = ?", (numero,))
                        autor = cursor.fetchone()[0]
                        status_texto = ("Proposta enviada — aguardando resposta" if autor == usuario_id
                                        else "Proposta recebida — aceite o horário")
                    else:
                        status_texto = {
                            "sem_proposta": "Aceita (sem proposta)",
                            "alteracao_solicitada": "Pediu alteração",
                            "confirmado": "Agendada"
                        }.get(situacao_agenda, "Aceita")
                else:
                    status_texto = status.capitalize()
                tabela.insert("", "end", iid=str(numero), values=(
                    numero, "Recebido" if recebido else "Enviado",
                    nome, habilidade or "Habilidade removida",
                    "Troca grátis" if tipo == "troca" else f"{custo} moedas", status_texto
                ))

            extras = 0
            if modo == "todos":
                cursor.execute("""
                    SELECT CASE WHEN aluno_id = ? THEN professor_id ELSE aluno_id END
                    FROM solicitacoes WHERE aluno_id = ? OR professor_id = ?
                """, (usuario_id, usuario_id, usuario_id))
                pessoas_com_pedido = {pessoa[0] for pessoa in cursor.fetchall()}
                for pessoa_id, nome, usuario, habilidades, reciproco in consultar_curtidas_recebidas(usuario_id):
                    if pessoa_id in pessoas_com_pedido:
                        continue
                    chave = f"curtida-{pessoa_id}"
                    if reciproco:
                        dados_linhas[chave] = ("match", pessoa_id, "sem_pedido", False, None)
                        status_extra = "BloomMatch ♡ (pedido não encontrado)"
                    else:
                        dados_linhas[chave] = ("curtida", pessoa_id, "aguardando", False)
                        status_extra = "Curtiu você ♡ (não é solicitação)"
                    tabela.insert("", "end", iid=chave, values=(
                        "—", "BloomMatch" if reciproco else "Curtida",
                        f"{nome} (@{usuario})", habilidades or "Habilidade disponível",
                        "Troca grátis" if reciproco else "5 moedas", status_extra
                    ))
                    extras += 1

            nomes_abas = {"todos": "Todas as solicitações", "recebidos": "Pedidos recebidos",
                          "enviados": "Pedidos enviados"}
            tela.itemconfig(texto_aba, text=f"{nomes_abas.get(modo, 'Solicitações')} ({len(registros) + extras})")
            if registros or extras:
                tela.itemconfig(aviso, text=(
                    f"{total_conta} pedido(s) nesta conta: {pendentes} pendente(s), "
                    f"{aceitos} aceito(s); {extras} curtida(s) sem pedido. "
                    "A coluna 'Origem' mostra se você enviou ou recebeu."
                ))
            else:
                cursor.execute("SELECT COUNT(*) FROM solicitacoes")
                total_banco = cursor.fetchone()[0]
                if total_banco:
                    texto = (f"Nenhum pedido nesta aba para @{usuario_logado['usuario']}. "
                             f"Este banco tem {total_banco} pedido(s) ao todo. "
                             "Confira a aba 'Todas' e a conta conectada.")
                else:
                    texto = ("Não há pedidos salvos neste bloomie.db. Confira se o arquivo "
                             "bloomie.db original está na mesma pasta do main.py. "
                             f"Pasta: {PASTA_PROJETO}. "
                             "Confira se abriu o Bloomie na pasta onde estão seus dados.")
                tela.itemconfig(aviso, text=texto)

        if selecionados and tabela.exists(selecionados[0]):
            tabela.selection_set(selecionados[0])
        else:
            itens = tabela.get_children()
            preferidos = [item for item in itens if dados_linhas[item][2] == "aceita"]
            if modo in ("todos", "recebidos", "enviados"):
                preferidos = ([item for item in itens if dados_linhas[item][2] == "pendente"]
                              + preferidos)
            escolhido = preferidos or itens
            if escolhido:
                tabela.selection_set(escolhido[0])
                tabela.focus(escolhido[0])
                tabela.see(escolhido[0])

    def atualizar():
        try:
            _atualizar_dados()
        except sqlite3.Error as erro:
            messagebox.showerror(
                "Bloomie - Minhas solicitações",
                f"Não foi possível consultar as solicitações.\nErro: {erro}\n"
                f"Banco: {os.path.join(PASTA_PROJETO, 'bloomie.db')}", parent=pedidos
            )
        finally:
            pendentes = listar_curtidas_sem_reciprocidade(usuario_logado["id"])
            tela.itemconfigure("botao_curtir_volta", state="normal" if pendentes else "hidden")
            atualizar_acoes()

    def mudar_aba(valor):
        aba.set(valor)
        atualizar()

    def pedido_selecionado():
        selecionados = tabela.selection()
        if not selecionados:
            messagebox.showwarning("Bloomie", "Selecione um item na lista.", parent=pedidos)
            return None
        return dados_linhas.get(selecionados[0])

    def combinar_aula():
        linha = pedido_selecionado()
        if linha is None:
            return
        if linha[0] == "match":
            pessoa_id, habilidade_id = linha[1], linha[4]
            if habilidade_id is None:
                sincronizar_matches_em_pedidos(usuario_logado["id"])
                criou = False
            else:
                criou = garantir_solicitacao_do_match(usuario_logado["id"], pessoa_id, habilidade_id)
            atualizar()
            if criou:
                messagebox.showinfo(
                    "Bloomie", "A solicitação da curtida recíproca foi registrada. "
                    "O professor pode aceitá-la em 'Recebidos'.", parent=pedidos
                )
            else:
                messagebox.showinfo(
                    "Bloomie", "Este BloomMatch não gerou um pedido novo. "
                    "Confira se existe uma solicitação antiga, cancelada ou recusada, "
                    "na aba 'Todas'.", parent=pedidos
                )
            return
        if linha[0] == "curtida":
            escolher_aula_com_pessoa(linha[1], pedidos, atualizar)
            return
        combinar_pedido_ou_aceitar(linha[1], pedidos, atualizar)

    def acao(tipo):
        linha = pedido_selecionado()
        if linha is None:
            return
        if linha[0] != "pedido":
            messagebox.showinfo("Bloomie", "Selecione uma solicitação para continuar.", parent=pedidos)
            return
        _, numero, status, recebido = linha
        if tipo == "aceitar" and status == "aceita":
            combinar_pedido_ou_aceitar(numero, pedidos, atualizar)
            return
        if tipo == "aceitar" and (status != "pendente" or not recebido):
            messagebox.showinfo("Bloomie", "Somente quem recebeu um pedido pendente pode aceitá-lo.", parent=pedidos)
            return
        if tipo == "cancelar" and recebido:
            messagebox.showwarning("Bloomie", "Você só pode cancelar os pedidos enviados.", parent=pedidos)
            return
        if tipo in ("recusar", "cancelar"):
            if status not in ("pendente", "aceita"):
                messagebox.showinfo("Bloomie", "Este pedido já foi finalizado.", parent=pedidos)
                return
            if not messagebox.askyesno(
                "Bloomie", "Deseja desistir desta aula? O pedido ficará salvo no histórico, "
                "mas não poderá mais ser agendado.", parent=pedidos
            ):
                return
        try:
            if tipo == "aceitar":
                mensagem = responder_solicitacao(numero, usuario_logado["id"], True)
            elif tipo == "recusar":
                mensagem = desistir_solicitacao(numero, usuario_logado["id"])
            elif tipo == "cancelar":
                mensagem = desistir_solicitacao(numero, usuario_logado["id"])
            else:
                confirmar_conclusao_aula(numero, pedidos, atualizar)
                return
            messagebox.showinfo("Bloomie 🌸", mensagem, parent=pedidos)
        except sqlite3.Error as erro:
            messagebox.showerror("Bloomie", f"Erro ao salvar no banco: {erro}", parent=pedidos)
        atualizar()

    def botao_no_fundo(x, y, largura, texto, comando, cor="#B98591", tag=None):
        altura = 43
        raio = 20
        marca = tag or f"acao_{x}_{y}"
        tela.create_oval(x, y, x + 2 * raio, y + altura, fill=cor,
                         outline="", tags=marca)
        tela.create_oval(x + largura - 2 * raio, y, x + largura, y + altura,
                         fill=cor, outline="", tags=marca)
        tela.create_rectangle(x + raio, y, x + largura - raio, y + altura,
                              fill=cor, outline="", tags=marca)
        tela.create_text(x + largura / 2, y + altura / 2, text=texto,
                         fill="white", font=("Arial", 11, "bold"), tags=marca)
        tela.tag_bind(marca, "<Button-1>", lambda evento: comando())
        tela.tag_bind(marca, "<Enter>", lambda evento: tela.config(cursor="hand2"))
        tela.tag_bind(marca, "<Leave>", lambda evento: tela.config(cursor=""))

    def sala_online_selecionada():
        linha = pedido_selecionado()
        if linha is None:
            return
        abrir_sala_online(linha[1], pedidos)

    texto_aba = tela.create_text(315, 195, text="Pedidos recebidos", anchor="nw",
                                 font=("Arial", 15, "bold"), fill="#713D4D")
    botao_no_fundo(1052, 185, 150, "Atualizar", atualizar, "#89998B", "atualizar_pedidos")
    botao_no_fundo(315, 640, 170, "Todas", lambda: mudar_aba("todos"), tag="aba_todos")
    botao_no_fundo(500, 640, 170, "Recebidos", lambda: mudar_aba("recebidos"), tag="aba_recebidos")
    botao_no_fundo(685, 640, 170, "Enviados", lambda: mudar_aba("enviados"), tag="aba_enviados")
    botao_no_fundo(
        870, 640, 170, "♡ Curtir de volta",
        lambda: abrir_curtir_de_volta_solicitacoes(pedidos, atualizar),
        "#89998B", "botao_curtir_volta"
    )
    tela.itemconfigure("botao_curtir_volta", state="hidden")
    botao_no_fundo(1055, 640, 170, "Voltar", pedidos.destroy, tag="voltar_pedidos")

    ajuda_selecao = tela.create_text(
        315, 616, text="selecione um pedido para gerenciar a aula",
        fill="#713D4D", font=("Arial", 10), anchor="nw"
    )

    def criar_botao_dinamico_canvas(largura, altura, cor, tag_prefixo):
        funcao_atual = [None]

        def configurar(texto, funcao, x, y):
            funcao_atual[0] = funcao
            tela.delete(tag_prefixo)
            raio = altura // 2
            tela.create_oval(x, y, x + 2 * raio, y + altura, fill=cor, outline="", tags=tag_prefixo)
            tela.create_oval(x + largura - 2 * raio, y, x + largura, y + altura, fill=cor, outline="", tags=tag_prefixo)
            tela.create_rectangle(x + raio, y, x + largura - raio, y + altura, fill=cor, outline="", tags=tag_prefixo)
            tela.create_text(x + largura / 2, y + altura / 2, text=texto, font=("Arial", 11, "bold"), fill="white", tags=tag_prefixo)

        def esconder():
            funcao_atual[0] = None
            tela.delete(tag_prefixo)

        tela.tag_bind(tag_prefixo, "<Button-1>", lambda e: funcao_atual[0]() if funcao_atual[0] else None)
        tela.tag_bind(tag_prefixo, "<Enter>", lambda e: tela.config(cursor="hand2"))
        tela.tag_bind(tag_prefixo, "<Leave>", lambda e: tela.config(cursor=""))
        return configurar, esconder

    configurar_principal_pedidos, esconder_principal_pedidos = criar_botao_dinamico_canvas(208, 43, "#89998B", "btn_din_prin")
    configurar_secundario_pedidos, esconder_secundario_pedidos = criar_botao_dinamico_canvas(208, 43, "#B98591", "btn_din_sec")

    def atualizar_acoes(evento=None):
        esconder_principal_pedidos()
        esconder_secundario_pedidos()
        selecao = tabela.selection()
        linha = dados_linhas.get(selecao[0]) if selecao else None
        if linha is None:
            tela.itemconfig(ajuda_selecao, text="selecione um pedido para ver as ações disponíveis")
            return
        principal = None
        secundario = None
        if linha[0] == "match":
            tela.itemconfig(ajuda_selecao, text="BloomMatch ♡: vocês curtiram habilidades um do outro; escolha como começar a troca")
            principal = ("Combinar troca grátis", combinar_aula)
            secundario = ("Oferecer aula", lambda pessoa_id=linha[1]: oferecer_aula_para_pessoa(
                pessoa_id, pedidos, atualizar))
        elif linha[0] == "curtida":
            tela.itemconfig(ajuda_selecao, text="sem match: peça uma aula ou ofereça uma habilidade sua, sem curtir")
            principal = ("Pedir aula (5 moedas)", combinar_aula)
            secundario = ("Dar aula", lambda: oferecer_aula_para_pessoa(
                linha[1], pedidos, atualizar))
        else:
            numero, status, recebido = linha[1:4]
            if status == "pendente":
                if recebido:
                    tela.itemconfig(ajuda_selecao, text="você recebeu esse pedido e pode responder agora")
                    principal = ("Aceitar pedido", lambda: acao("aceitar"))
                    secundario = ("Recusar pedido", lambda: acao("recusar"))
                else:
                    tela.itemconfig(ajuda_selecao, text="pedido enviado: aguardando a outra pessoa aceitar")
                    secundario = ("Cancelar pedido", lambda: acao("cancelar"))
            elif status == "aceita":
                try:
                    agendamento = banco.consultar_agendamento(numero, usuario_logado["id"])
                except sqlite3.Error:
                    agendamento = None
                situacao = (agendamento or {}).get("situacao_agendamento") or "sem_proposta"
                if situacao == "confirmado":
                    if agendamento and agendamento.get("modalidade_aula") == "online":
                        tela.itemconfig(ajuda_selecao, text="aula online agendada: entre na sala online para assistir e confirmar a conclusão")
                        principal = ("Sala online", sala_online_selecionada)
                    else:
                        tela.itemconfig(ajuda_selecao, text="aula presencial agendada: depois da aula, professor e aluno confirmam separadamente")
                        principal = ("Ver agendamento", combinar_aula)
                    professor = agendamento and agendamento.get("professor_id") == usuario_logado["id"]
                    confirmado = (agendamento.get("confirmado_professor") if professor
                                  else (agendamento or {}).get("confirmado_aluno"))
                    if not confirmado:
                        secundario = ("Marcar aula dada" if professor else "Confirmar aula recebida",
                                      lambda: acao("confirmar"))
                    else:
                        tela.itemconfig(ajuda_selecao, text="você já confirmou essa aula; aguardando a outra pessoa")
                elif situacao == "proposta" and agendamento and agendamento.get("proposta_por") != usuario_logado["id"]:
                    tela.itemconfig(ajuda_selecao, text="você recebeu uma proposta: aceite o horário ou peça alteração")
                    principal = ("Aceitar horário", lambda pid=numero: responder_proposta_horario(pid, pedidos, atualizar, True))
                    secundario = ("Pedir alteração", lambda pid=numero: responder_proposta_horario(pid, pedidos, atualizar, False))
                else:
                    tela.itemconfig(ajuda_selecao, text=("você enviou uma proposta. aguarde a resposta da outra pessoa"
                                              if situacao == "proposta" else
                                              "pedido aceito: abra combinar aula para escolher o horário"))
                    principal = ("Ver proposta" if situacao == "proposta" else "Combinar aula", combinar_aula)
                    secundario = ("Desistir da aula", lambda: acao("recusar" if recebido else "cancelar"))
            elif status == "concluida":
                tela.itemconfig(ajuda_selecao, text="aula concluída: consulte os detalhes ou faça um novo pedido")
                principal = ("Ver detalhes", lambda pid=numero: ver_detalhes_aula_concluida(pid, pedidos))
                secundario = ("Nova aula", lambda pid=numero: pedir_nova_aula_de_pedido(pid, pedidos, atualizar))
            else:
                tela.itemconfig(ajuda_selecao, text="pedido cancelado ou recusado: não pode ser agendado")

        if principal:
            configurar_principal_pedidos(principal[0], principal[1], 593 if secundario else 670, 700)
        if secundario:
            configurar_secundario_pedidos(secundario[0], secundario[1], 818 if principal else 670, 700)

    tabela.bind("<<TreeviewSelect>>", atualizar_acoes)
    tabela.bind("<Double-1>", lambda evento: combinar_aula())
    atualizar()

def dar_recompensa(usuario_id, missao, moedas):
    #ignore evita ganhar a mesma recompensa duas vezes
    #zero significa que a missão já tinha sido concluída
    return banco.registrar_recompensa(usuario_id, missao, moedas)


def verificar_missoes_extras(usuario_id):

    cursor.execute("""
        SELECT h.usuario_id
        FROM bloommatch_reacoes r
        JOIN habilidades h ON h.id = r.habilidade_id
        WHERE r.usuario_id = ? AND r.acao = 'curti'
        AND h.usuario_id != ?
    """, (usuario_id, usuario_id))

    pessoas_curtidas = [linha[0] for linha in cursor.fetchall()]

    for pessoa in pessoas_curtidas:
        #vê se a outra pessoa também curtiu uma habilidade dela
        cursor.execute("""
            SELECT 1 FROM bloommatch_reacoes r
            JOIN habilidades h ON h.id = r.habilidade_id
            WHERE r.usuario_id = ? AND h.usuario_id = ?
            AND r.acao = 'curti'
            LIMIT 1
        """, (pessoa, usuario_id))

        if cursor.fetchone():
            dar_recompensa(usuario_id, "primeiro_match", 5)
            break


    cursor.execute("""
        SELECT 1 FROM solicitacoes
        WHERE aluno_id = ? AND status = 'concluida'
        LIMIT 1
    """, (usuario_id,))

    if cursor.fetchone():
        dar_recompensa(usuario_id, "primeira_aula", 10)


    cursor.execute("""
        SELECT 1 FROM solicitacoes
        WHERE professor_id = ? AND status = 'concluida'
        LIMIT 1
    """, (usuario_id,))

    if cursor.fetchone():
        dar_recompensa(usuario_id, "primeira_aula_ensinada", 10)


def abrir_bloomcoins():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    janela_coins = tk.Toplevel(janela)
    janela_coins.title("Bloomie - BloomCoins")
    janela_coins.geometry("1300x800")
    janela_coins.resizable(False, False)

    tela = tk.Canvas(janela_coins, width=1300, height=800, bg="#F8E8F0", highlightthickness=0)
    tela.pack()
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fundo_bloomie_funcionalidades.gif")

    try:
        imagem = tk.PhotoImage(file=caminho)
        janela_coins.imagem_fundo = imagem
        tela.create_image(0, 0, image=imagem, anchor="nw")
    except (tk.TclError, OSError) as erro:
        print("Não foi possível carregar o fundo:", erro)

    tela.create_text(320, 65, text="Minhas BloomCoins 🪙", font=("Arial", 26, "bold"),
                     fill="#713D4D", anchor="nw")
    tela.create_text(320, 115, text="Acompanhe suas moedas e as recompensas recebidas.",
                     font=("Arial", 12), fill="#594C50", anchor="nw")

    def atualizar():
        tela.delete("dados_coins")
        saldo = consultar_saldo(usuario_logado["id"])
        tela.create_rectangle(320, 190, 1210, 300, fill="#FFF7F3", outline="", tags="dados_coins")
        tela.create_text(350, 220, text=f"Saldo: {saldo} BloomCoins", font=("Arial", 21, "bold"),
                         fill="#713D4D", anchor="nw", tags="dados_coins")
        tela.create_text(320, 345, text="Histórico de moedas", font=("Arial", 18, "bold"),
                         fill="#713D4D", anchor="nw", tags="dados_coins")
        movimentos = banco.consultar_historico_bloomcoins(usuario_logado["id"]) #mostra as últimas movimentações de moedas
        if not movimentos:
            tela.create_text(345, 395, text="Ainda não há movimentações registradas.",
                             font=("Arial", 12), fill="#594C50", anchor="nw", tags="dados_coins")
        for indice, (quantidade, motivo, data) in enumerate(movimentos):
            y = 395 + indice * 41
            sinal = "+" if quantidade > 0 else ""
            tela.create_text(345, y, text=f"{motivo}  |  {data}  |  {sinal}{quantidade} moedas",
                             font=("Arial", 11), fill="#594C50", anchor="nw", tags="dados_coins")

    atualizar()
    botao_suave(janela_coins, "Atualizar", atualizar).place(x=440, y=720)
    botao_suave(janela_coins, "Voltar", janela_coins.destroy).place(x=660, y=720)


def abrir_missoes_bloomie():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    missoes = tk.Toplevel(janela)
    missoes.title("Bloomie - Missões")
    missoes.geometry("1300x800")
    missoes.resizable(False, False)

    tela = tk.Canvas(missoes, width=1300, height=800, bg="#F8E8F0", highlightthickness=0)
    tela.pack()
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fundo_bloomie_funcionalidades.gif")

    try:
        imagem = tk.PhotoImage(file=caminho)
        missoes.imagem_fundo = imagem
        tela.create_image(0, 0, image=imagem, anchor="nw")
    except (tk.TclError, OSError) as erro:
        print("Não foi possível carregar o fundo:", erro)

    def cartao(x, y, largura, altura, cor, tag="missao"):
        raio = 22
        tela.create_oval(x, y, x + 2*raio, y + altura, fill=cor, outline="", tags=tag)
        tela.create_oval(x + largura - 2*raio, y, x + largura, y + altura, fill=cor, outline="", tags=tag)
        tela.create_rectangle(x + raio, y, x + largura - raio, y + altura, fill=cor, outline="", tags=tag)

    tela.create_text(320, 65, text="Missões Bloomie 🌸", font=("Arial", 25, "bold"),
                    fill="#713D4D", anchor="nw")
    tela.create_text(320, 115, text="Complete atividades e ganhe BloomCoins!",
                    font=("Arial", 12), fill="#594C50", anchor="nw")

    def atualizar():
        verificar_missoes_extras(usuario_logado["id"]) #libera as moedas das missões que já foram cumpridas
        tela.delete("missao")
        saldo = consultar_saldo(usuario_logado["id"])
        tela.create_text(1205, 72, text=f"🪙 {saldo} moedas",
                         font=("Arial", 13, "bold"), fill="#713D4D", anchor="ne", tags="missao")

        cursor.execute("SELECT missao FROM missoes_concluidas WHERE usuario_id = ?", (usuario_logado["id"],))
        concluidas = {linha[0] for linha in cursor.fetchall()} #set guarda as missões sem repetir nomes

        lista = [
            ("perfil_completo", "Complete seu perfil", "Preencha sobre você, cidade, interesses e o que quer aprender.", 5),
            ("primeira_habilidade", "Compartilhe sua primeira habilidade", "Cadastre uma habilidade que você pode ensinar.", 5),
            ("primeiro_match", "Seu primeiro BloomMatch", "Consiga uma curtida recíproca.", 5),
            ("primeira_aula", "Sua primeira aula", "Conclua uma aula como aluno.", 10),
            ("primeira_aula_ensinada", "Primeira aula ensinada", "Ensine uma aula e confirme a conclusão.", 10)
        ]
        for indice, (chave, titulo, descricao, recompensa) in enumerate(lista):
            y = 165 + indice * 106
            cartao(310, y, 920, 96, "#FFF7F3")
            tela.create_text(337, y+18, text=titulo, anchor="nw",
                            font=("Arial", 16, "bold"), fill="#713D4D", tags="missao")
            tela.create_text(337, y+54, text=descricao, anchor="nw",
                            font=("Arial", 11), fill="#594C50", tags="missao")
            situacao = "Concluída ✓" if chave in concluidas else f"+{recompensa} BloomCoins"
            tela.create_text(1195, y+18, text=situacao, anchor="ne",
                            font=("Arial", 12, "bold"), fill="#89998B", tags="missao")


    atualizar()
    atualizar_botao = botao_suave(missoes, "Atualizar missões", atualizar)
    atualizar_botao.place(x=440, y=710)
    fechar_botao = botao_suave(missoes, "Voltar", missoes.destroy)
    fechar_botao.place(x=665, y=710)


def abrir_jardim_conquistas():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    usuario_id = usuario_logado["id"]

    cursor.execute(
        "SELECT missao FROM missoes_concluidas WHERE usuario_id = ?",
        (usuario_id,)
    )

    missoes = []
    for linha in cursor.fetchall():
        missoes.append(linha[0])

    cursor.execute(
        "SELECT id FROM habilidades WHERE usuario_id = ?",
        (usuario_id,)
    )

    minhas_habilidades = []
    for linha in cursor.fetchall():
        minhas_habilidades.append(linha[0])

    cursor.execute(
        "SELECT habilidade_id FROM bloommatch_reacoes WHERE usuario_id = ? AND acao = 'curti'",
        (usuario_id,)
    )
    curtidas = cursor.fetchall()
    tem_match = False

    for curtida in curtidas:
        cursor.execute(
            "SELECT usuario_id FROM habilidades WHERE id = ?",
            (curtida[0],)
        )
        dono = cursor.fetchone()

        if dono and dono[0] != usuario_id:
            for habilidade_id in minhas_habilidades:
                cursor.execute(
                    "SELECT acao FROM bloommatch_reacoes WHERE usuario_id = ? AND habilidade_id = ?",
                    (dono[0], habilidade_id)
                )
                resposta = cursor.fetchone()

                if resposta and resposta[0] == "curti":
                    tem_match = True
                    break

        if tem_match:
            break

    cursor.execute(
        "SELECT status FROM solicitacoes WHERE aluno_id = ? OR professor_id = ?",
        (usuario_id, usuario_id)
    )

    primeira_aula = False
    for pedido in cursor.fetchall():
        if pedido[0] == "concluida":
            primeira_aula = True
            break

    conquistas = [
        ("Primeira Semente", "Complete seu perfil.", "🌱", "perfil_completo" in missoes),
        ("Primeira Flor", "Compartilhe sua primeira habilidade.", "🌸", "primeira_habilidade" in missoes),
        ("Conexão Especial", "Consiga seu primeiro BloomMatch.", "♡", tem_match),
        ("Conhecimento Compartilhado", "Conclua sua primeira aula.", "📖", primeira_aula)
    ]

    jardim = tk.Toplevel(janela)
    jardim.title("Bloomie - Jardim de Conquistas")
    jardim.geometry("1300x800")
    jardim.resizable(False, False)

    tela = tk.Canvas(
        jardim, width=1300, height=800,
        highlightthickness=0
    )
    tela.pack()

    imagem = carregar_fundo(
        "fundo_bloomie_funcionalidades.gif", 1300, 800
    )
    jardim.imagem_fundo = imagem
    tela.create_image(0, 0, image=imagem, anchor="nw")

    tela.create_text(
        650, 115,
        text="Jardim de Conquistas 🌱",
        font=("Georgia", 28, "bold"),
        fill="#60765F"
    )

    tela.create_text(
        650, 158,
        text="Veja as conquistas que você já desbloqueou.",
        font=("Arial", 13),
        fill="#746962"
    )

    def arredondado(x, y, largura, altura, cor, borda="", tag=None):
        r = 20
        tela.create_polygon(
            x+r, y,
            x+largura-r, y,
            x+largura, y,
            x+largura, y+r,
            x+largura, y+altura-r,
            x+largura, y+altura,
            x+largura-r, y+altura,
            x+r, y+altura,
            x, y+altura,
            x, y+altura-r,
            x, y+r,
            x, y,
            smooth=True,
            splinesteps=22,
            fill=cor,
            outline=borda,
            width=1.5,
            tags=tag
        )

    posicoes = [
        (345, 207),
        (660, 207),
        (345, 469),
        (660, 469)
    ]

    for i in range(len(conquistas)):
        titulo, descricao, icone, desbloqueada = conquistas[i]
        x, y = posicoes[i]

        if desbloqueada:
            cor_fundo = "#F1F1E6"
            cor_borda = "#D2D2BB"
            cor_titulo = "#657B63"
            cor_status = "#D9DFC9"
            texto_status = "Desbloqueada ✓"
        else:
            cor_fundo = "#FBECE7"
            cor_borda = "#ECC4BB"
            cor_titulo = "#966963"
            cor_status = "#F0D1C9"
            texto_status = "🔒 Bloqueada"

        arredondado(
            x, y, 295, 242,
            cor_fundo, cor_borda
        )

        tela.create_oval(
            x+115, y+22,
            x+180, y+89,
            fill="#E6E8D9" if desbloqueada else "#F5DDD7",
            outline=""
        )

        tela.create_text(
            x+147, y+58,
            text=icone,
            font=("Segoe UI Emoji", 39),
            fill=cor_titulo
        )

        tela.create_text(
            x+147, y+128,
            text=titulo,
            font=("Georgia", 15, "bold"),
            fill=cor_titulo,
            width=270,
            justify="center"
        )

        tela.create_text(
            x+147, y+170,
            text=descricao,
            font=("Arial", 11),
            fill="#746962",
            width=248,
            justify="center"
        )

        arredondado(
            x+68, y+207,
            160, 29,
            cor_status
        )

        tela.create_text(
            x+148, y+221,
            text=texto_status,
            font=("Arial", 10, "bold"),
            fill=cor_titulo
        )

    arredondado(
        555, 735, 190, 43,
        "#CA918B",
        tag="voltar_jardim"
    )

    tela.create_text(
        650, 756,
        text="←  Voltar",
        font=("Georgia", 15, "bold"),
        fill="white",
        tags="voltar_jardim"
    )

    tela.tag_bind(
        "voltar_jardim", "<Button-1>",
        lambda evento: jardim.destroy()
    )
    tela.tag_bind(
        "voltar_jardim", "<Enter>",
        lambda evento: tela.config(cursor="hand2")
    )
    tela.tag_bind(
        "voltar_jardim", "<Leave>",
        lambda evento: tela.config(cursor="")
    )


def abrir_historico_trocas():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    historico = tk.Toplevel(janela)
    historico.title("Bloomie - Histórico de Trocas")
    historico.geometry("1300x800")
    historico.resizable(False, False)

    tela = tk.Canvas(historico, width=1300, height=800, highlightthickness=0)
    tela.pack()
    imagem = carregar_fundo("fundo_bloomie_funcionalidades.gif", 1300, 800)
    historico.imagem_fundo = imagem
    tela.create_image(0, 0, image=imagem, anchor="nw")

    tela.create_text(320, 70, text="Histórico de Trocas",
                     font=("Arial", 26, "bold"), fill="#536B5C", anchor="nw")
    tela.create_text(320, 120, text="Aulas concluídas que você ensinou ou aprendeu.",
                     font=("Arial", 12), fill="#594C50", anchor="nw")

    colunas = ("papel", "habilidade", "pessoa", "modalidade")
    tabela = ttk.Treeview(historico, columns=colunas, show="headings", height=11)
    for coluna, titulo, largura in (
        ("papel", "Participação", 140),
        ("habilidade", "Habilidade", 330),
        ("pessoa", "Outra pessoa", 260),
        ("modalidade", "Tipo de aula", 180)
    ):
        tabela.heading(coluna, text=titulo)
        tabela.column(coluna, width=largura, anchor="center")
    tabela.place(x=320, y=205, width=920, height=405)

    def atualizar():
        for item in tabela.get_children():
            tabela.delete(item)

        usuario_id = usuario_logado["id"]
        cursor.execute("""
            SELECT s.aluno_id, s.professor_id, h.habilidade,
                   aluno.nome, professor.nome, s.tipo, s.custo_bloomcoins
            FROM solicitacoes s
            LEFT JOIN habilidades h ON h.id = s.habilidade_id
            LEFT JOIN usuarios aluno ON aluno.id = s.aluno_id
            LEFT JOIN usuarios professor ON professor.id = s.professor_id
            WHERE (s.aluno_id = ? OR s.professor_id = ?)
              AND s.status = 'concluida'
            ORDER BY s.id DESC
        """, (usuario_id, usuario_id))

        registros = cursor.fetchall()
        for aluno_id, professor_id, habilidade, aluno, professor, tipo, custo in registros:
            if usuario_id == aluno_id:
                participacao = "Aprendi"
                outra_pessoa = professor or "Conta excluída"
            else:
                participacao = "Ensinei"
                outra_pessoa = aluno or "Conta excluída"

            modalidade = "Troca gratuita" if tipo == "troca" else f"{custo} BloomCoins"
            tabela.insert("", "end", values=(
                participacao, habilidade or "Habilidade excluída",
                outra_pessoa, modalidade
            ))

        aviso = "Nenhuma aula concluída ainda." if not registros else ""
        tela.itemconfig(texto_vazio, text=aviso)

    texto_vazio = tela.create_text(
        780, 650, text="", font=("Arial", 12), fill="#594C50"
    )
    botao_suave(historico, "Atualizar", atualizar, cor="#89998B").place(x=435, y=700)
    botao_suave(historico, "Voltar", historico.destroy).place(x=655, y=700)
    atualizar()


def consultar_saldo(usuario_id):
    #pega o saldo encontrado na consulta
    return banco.consultar_saldo(usuario_id)


def proteger_senha(senha):
    salt = os.urandom(16) #gera uma proteção diferente pra cada senha

    hash_senha = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        600000
    ) #transforma a senha antes de salvar no banco

    return salt.hex() + ":" + hash_senha.hex()

def verificar_senha(senha, senha_salva):
    salt_hex, hash_hex = senha_salva.split(":")

    salt = bytes.fromhex(salt_hex)
    hash_original = bytes.fromhex(hash_hex)

    hash_digitado = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        600000
    )

    return hmac.compare_digest(hash_digitado, hash_original) #compara a senha digitada com a cadastrada



def criar_codigo_recuperacao(usuario_id):
    #guarda só o hash do código; o código original aparece uma vez
    import secrets
    codigo = secrets.token_urlsafe(24)
    cursor.execute(
        "UPDATE usuarios SET recuperacao_hash = ? WHERE id = ?",
        (proteger_senha(codigo), usuario_id)
    )
    if cursor.rowcount != 1:
        conexao.rollback()
        raise ValueError("Conta não encontrada para recuperação.")
    conexao.commit()
    return codigo


def exibir_codigo_recuperacao(codigo, parent):
    janela_codigo = tk.Toplevel(parent)
    janela_codigo.title("Bloomie - Código de recuperação")
    janela_codigo.geometry("630x315")
    janela_codigo.resizable(False, False)
    janela_codigo.configure(bg="#FFF7F3")
    aplicar_fundo_funcionalidades(janela_codigo, 630, 315)
    janela_codigo.lift()
    tk.Label(
        janela_codigo, text="Seu código de recuperação 🌸",
        font=("Arial", 19, "bold"), fg="#713D4D", bg="#FFF7F3"
    ).pack(pady=(23, 12))
    tk.Label(
        janela_codigo,
        text="Guarde este código em um lugar seguro. Ele é mostrado uma única vez.\n"
             "Se esquecer a senha, você precisará dele para criar uma nova.",
        font=("Arial", 11), fg="#594C50", bg="#FFF7F3",
        justify="center"
    ).pack(pady=8)
    campo_codigo = tk.Entry(
        janela_codigo, font=("Consolas", 14), justify="center",
        bg="white", fg="#713D4D", relief="flat", bd=5
    )
    campo_codigo.insert(0, codigo)
    campo_codigo.configure(state="readonly")
    campo_codigo.pack(padx=28, fill="x", pady=(10, 14))

    def copiar():
        janela_codigo.clipboard_clear()
        janela_codigo.clipboard_append(codigo)
        messagebox.showinfo("Bloomie", "Código copiado! Guarde em local seguro.", parent=janela_codigo)

    botoes = tk.Frame(janela_codigo, bg="#FFF7F3")
    botoes.pack()
    botao_suave(botoes, "Copiar código", copiar, largura=180, cor="#89998B").pack(side="left", padx=8)
    botao_suave(botoes, "Já guardei", janela_codigo.destroy, largura=180).pack(side="left", padx=8)


def abrir_frase_seguranca(parent):
    if usuario_logado is None:
        return
    popup = tk.Toplevel(parent)
    popup.title("Bloomie - Frase de segurança")
    popup.geometry("590x465")
    popup.resizable(False, False)
    popup.transient(parent)

    tela = tk.Canvas(popup, width=590, height=465, bg="#F1E2DE", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 590, 465)
        popup.fundo_frase = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    tela.create_text(295, 38, text="Frase de segurança 🌸", font=("Arial", 21, "bold"), fill="#713D4D")
    tela.create_text(
        295, 84,
        text="Ela será usada para recuperar sua senha caso você esqueça.\n"
             "Escolha uma frase privada e difícil de adivinhar (mínimo 12 caracteres).",
        fill="#594C50", justify="center", font=("Arial", 10)
    )

    campos = []
    for indice, (rotulo, y) in enumerate((
        ("Senha atual", 128),
        ("Nova frase de segurança", 206),
        ("Confirme a frase", 284)
    )):
        tela.create_text(70, y, text=rotulo, fill="#713D4D", font=("Arial", 11, "bold"), anchor="nw")
        fundo_campo(tela, 68, y + 23, 390, 36)
        campo = tk.Entry(popup, show="*", font=("Arial", 12), bg="#FFF7F3",
                         fg="#594C50", insertbackground="#594C50", relief="flat", bd=0)
        campo.place(x=82, y=y + 27, width=362, height=28)

        estado = [False]
        botao_ver = tk.Button(
            popup, text="◉", font=("Arial", 11), bg="#E9D8D3", fg="#713D4D",
            activebackground="#D5B8B1", relief="flat", bd=0, cursor="hand2"
        )
        def alternar(campo=campo, estado=estado, botao=botao_ver):
            estado[0] = not estado[0]
            campo.configure(show="" if estado[0] else "*")
            botao.configure(text="◌" if estado[0] else "◉")
        botao_ver.configure(command=alternar)
        botao_ver.place(x=468, y=y + 25, width=45, height=32)
        campos.append(campo)

    def salvar_frase():
        senha, frase, confirmacao = (c.get() for c in campos)
        if not senha or not frase or not confirmacao:
            messagebox.showwarning("Bloomie", "Preencha todos os campos.", parent=popup)
            return
        if len(frase) < 12 or frase != confirmacao:
            messagebox.showwarning("Bloomie", "Digite a mesma frase duas vezes (mínimo 12 caracteres).", parent=popup)
            return
        cursor.execute("SELECT senha_hash FROM usuarios WHERE id=?", (usuario_logado["id"],))
        registro = cursor.fetchone()
        if not registro or not verificar_senha(senha, registro[0]):
            messagebox.showerror("Bloomie", "Senha atual incorreta. Nada foi alterado.", parent=popup)
            return
        try:
            cursor.execute("UPDATE usuarios SET frase_seguranca_hash=? WHERE id=?",
                           (proteger_senha(frase), usuario_logado["id"]))
            conexao.commit()
        except sqlite3.Error as erro:
            conexao.rollback()
            messagebox.showerror("Bloomie", str(erro), parent=popup)
            return
        popup.destroy()
        messagebox.showinfo("Bloomie", "Frase de segurança configurada! Guarde-a em lugar seguro.", parent=parent)

    for atual, proximo in zip(campos, campos[1:]):
        atual.bind("<Return>", lambda evento, campo=proximo: (campo.focus_set(), "break")[1])
    campos[-1].bind("<Return>", lambda evento: (salvar_frase(), "break")[1])

    # Botão arredondado desenhado direto no Canvas para não ter fundo quadrado
    tag_btn = "btn_salvar_frase"
    x, y, larg, alt, r = 195, 382, 200, 42, 21
    tela.create_oval(x, y, x + 2*r, y + alt, fill="#89998B", outline="", tags=tag_btn)
    tela.create_oval(x + larg - 2*r, y, x + larg, y + alt, fill="#89998B", outline="", tags=tag_btn)
    tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill="#89998B", outline="", tags=tag_btn)
    tela.create_text(x + larg/2, y + alt/2, text="Salvar frase", font=("Arial", 11, "bold"), fill="white", tags=tag_btn)
    tela.tag_bind(tag_btn, "<Button-1>", lambda e: salvar_frase())
    tela.tag_bind(tag_btn, "<Enter>", lambda e: tela.config(cursor="hand2"))
    tela.tag_bind(tag_btn, "<Leave>", lambda e: tela.config(cursor=""))

    campos[0].focus_set()


def abrir_recuperacao_senha(parent):
    recuperar = tk.Toplevel(parent)
    recuperar.title("Bloomie - Esqueci minha senha")
    recuperar.geometry("620x570")
    recuperar.resizable(False, False)
    recuperar.lift()

    tela = tk.Canvas(recuperar, width=620, height=570, bg="#F1E2DE", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 620, 570)
        recuperar.fundo_rec = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    tela.create_text(310, 42, text="Recuperar senha 🌸", font=("Arial", 22, "bold"), fill="#713D4D")
    tela.create_text(
        310, 82,
        text="Informe seu usuário e a frase de segurança cadastrada nas configurações.",
        fill="#594C50", font=("Arial", 11), width=520, justify="center"
    )

    entradas = []
    perguntas = (
        ("Nome de usuário", False, 120),
        ("Frase de segurança", True, 200),
        ("Nova senha (mínimo 8 caracteres)", True, 280),
        ("Repetir nova senha", True, 360)
    )
    for titulo, oculto, y in perguntas:
        tela.create_text(60, y, text=titulo, fill="#713D4D", font=("Arial", 11, "bold"), anchor="nw")
        larg_campo = 445 if oculto else 500
        fundo_campo(tela, 58, y + 24, larg_campo, 38)
        entrada = tk.Entry(
            recuperar, font=("Arial", 12), bg="#FFF7F3", fg="#594C50",
            relief="flat", bd=0, show="*" if oculto else ""
        )
        entrada.place(x=74, y=y + 29, width=larg_campo - 32, height=28)

        if oculto:
            estado_visivel = [False]
            botao_ver = tk.Button(
                recuperar, text="◉", font=("Arial", 11), bg="#E9D8D3",
                fg="#713D4D", activebackground="#D5B8B1", relief="flat", bd=0, cursor="hand2"
            )
            def alternar_visibilidade(campo=entrada, estado=estado_visivel, botao=botao_ver):
                estado[0] = not estado[0]
                campo.configure(show="" if estado[0] else "*")
                botao.configure(text="◌" if estado[0] else "◉")
            botao_ver.configure(command=alternar_visibilidade)
            botao_ver.place(x=512, y=y + 26, width=45, height=34)
        entradas.append(entrada)

    for atual, proximo in zip(entradas, entradas[1:]):
        atual.bind("<Return>", lambda evento, campo=proximo: (campo.focus_set(), "break")[1])

    def redefinir():
        usuario, frase, senha, confirmacao = (c.get().strip() for c in entradas)
        if not usuario or not frase or not senha or not confirmacao:
            messagebox.showwarning("Bloomie", "Preencha todos os campos.", parent=recuperar)
            return
        if len(senha) < 8 or senha != confirmacao:
            messagebox.showwarning("Bloomie", "Use uma senha com pelo menos 8 caracteres e confirme igual.", parent=recuperar)
            return
        cursor.execute("SELECT id, frase_seguranca_hash FROM usuarios WHERE usuario = ?", (usuario,))
        dados = cursor.fetchone()
        if not (dados and dados[1] and verificar_senha(frase, dados[1])):
            messagebox.showerror("Bloomie", "Frase de segurança inválida.", parent=recuperar)
            return
        try:
            cursor.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (proteger_senha(senha), dados[0]))
            cursor.execute("DELETE FROM sessao WHERE usuario_id = ?", (dados[0],))
            conexao.commit()
        except sqlite3.Error as erro:
            conexao.rollback()
            messagebox.showerror("Bloomie", f"Não foi possível salvar: {erro}", parent=recuperar)
            return
        recuperar.destroy()
        messagebox.showinfo("Bloomie 🌸", "Senha alterada! Entre com a nova senha.", parent=parent)

    entradas[-1].bind("<Return>", lambda evento: (redefinir(), "break")[1])

    tag_btn = "btn_redefinir"
    x, y, larg, alt, r = 195, 470, 230, 44, 22
    tela.create_oval(x, y, x + 2*r, y + alt, fill="#B98591", outline="", tags=tag_btn)
    tela.create_oval(x + larg - 2*r, y, x + larg, y + alt, fill="#B98591", outline="", tags=tag_btn)
    tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill="#B98591", outline="", tags=tag_btn)
    tela.create_text(x + larg/2, y + alt/2, text="Redefinir senha", font=("Arial", 11, "bold"), fill="white", tags=tag_btn)
    tela.tag_bind(tag_btn, "<Button-1>", lambda e: redefinir())
    tela.tag_bind(tag_btn, "<Enter>", lambda e: tela.config(cursor="hand2"))
    tela.tag_bind(tag_btn, "<Leave>", lambda e: tela.config(cursor=""))

    entradas[0].focus_set()


janela = tk.Tk()
janela.title("Bloomie")
janela.geometry("1300x800")
janela.resizable(False, False) #impede que a janela seja redimensionada


usuario_logado = None #guarda os dados de cada usuario que entrou na conta

def salvar_sessao(usuario_id):
    cursor.execute(
    "INSERT OR REPLACE INTO SESSAO (id, usuario_id) VALUES (1, ?)",
    (usuario_id,)
    )
    conexao.commit() #guarda o usuario conectado pra ele nao precisar fazer login de novo



def botao_suave(pai, texto, comando, largura=190, altura=40, cor="#B98591"):
    botao = tk.Canvas(pai, width=largura, height=altura, bg=pai.cget("bg"),
                      highlightthickness=0, bd=0, cursor="hand2")
    raio = min(18, altura // 2)
    botao.create_oval(0, 0, 2 * raio, altura, fill=cor, outline="", tags="clicar")
    botao.create_oval(largura - 2 * raio, 0, largura, altura,
                      fill=cor, outline="", tags="clicar")
    botao.create_rectangle(raio, 0, largura - raio, altura,
                           fill=cor, outline="", tags="clicar")
    botao.create_text(largura / 2, altura / 2, text=texto,
                      font=("Arial", 11, "bold"), fill="white", tags="clicar")
    botao.tag_bind("clicar", "<Button-1>", lambda evento: comando())
    return botao


def botao_suave_dinamico(pai, largura=190, altura=40, cor="#89998B"):
    #o mesmo botão arredondado, só muda o texto e a função quando trocar de seleção
    botao = tk.Canvas(pai, width=largura, height=altura, bg=pai.cget("bg"),
                      highlightthickness=0, bd=0, cursor="hand2")
    funcao_atual = [None]

    def configurar(texto, funcao):
        funcao_atual[0] = funcao
        botao.delete("all")
        raio = altura // 2
        botao.create_oval(0, 0, 2 * raio, altura, fill=cor, outline="")
        botao.create_oval(largura - 2 * raio, 0, largura, altura,
                          fill=cor, outline="")
        botao.create_rectangle(raio, 0, largura - raio, altura,
                               fill=cor, outline="")
        botao.create_text(largura / 2, altura / 2, text=texto,
                          font=("Arial", 10, "bold"), fill="white")

    def clicar(evento):
        if funcao_atual[0] is not None:
            funcao_atual[0]()

    botao.bind("<Button-1>", clicar)
    return botao, configurar


def formatar_entrada_data_hora(campo, tipo):
    #as barras e os dois pontos aparecem enquanto a pessoa digita
    limite = 8 if tipo == "data" else 4

    def so_numeros(texto):
        return "".join(caractere for caractere in texto if caractere.isdigit())[:limite]

    def montar(numeros):
        texto = numeros[:2]
        if len(numeros) > 2:
            texto += ("/" if tipo == "data" else ":") + numeros[2:4]
        if tipo == "data" and len(numeros) > 4:
            texto += "/" + numeros[4:8]
        return texto

    def posicao_depois_dos_digitos(texto, quantidade):
        #mantém o cursor no lugar mesmo depois de colocar as barras
        if quantidade <= 0:
            return 0
        encontrados = 0
        for indice, caractere in enumerate(texto):
            if caractere.isdigit():
                encontrados += 1
                if encontrados == quantidade:
                    return indice + 1
        return len(texto)

    def aplicar(numeros, cursor_em):
        novo_texto = montar(numeros[:limite])
        campo.delete(0, tk.END)
        campo.insert(0, novo_texto)
        campo.icursor(posicao_depois_dos_digitos(novo_texto, cursor_em))

    def selecao_ou_cursor():
        try:
            return campo.index("sel.first"), campo.index("sel.last")
        except tk.TclError:
            posicao = campo.index(tk.INSERT)
            return posicao, posicao

    def ao_digitar(evento):
        #deixa navegar com as setas, usar tab e os atalhos ctrl+a / ctrl+v
        if evento.state & 0x4:
            return None
        texto = campo.get()
        numeros = so_numeros(texto)
        inicio, fim = selecao_ou_cursor()
        antes = sum(c.isdigit() for c in texto[:inicio])
        depois = sum(c.isdigit() for c in texto[:fim])

        if evento.char and evento.char.isdigit():
            if len(numeros) >= limite and antes == depois:
                return "break"
            novo = numeros[:antes] + evento.char + numeros[depois:]
            aplicar(novo, antes + 1)
            return "break"
        if evento.keysym in ("BackSpace", "Delete"):
            if inicio != fim:
                novo = numeros[:antes] + numeros[depois:]
                posicao = antes
            elif evento.keysym == "BackSpace":
                novo = numeros[:max(0, antes - 1)] + numeros[antes:]
                posicao = max(0, antes - 1)
            else:
                novo = numeros[:antes] + numeros[antes + 1:]
                posicao = antes
            aplicar(novo, posicao)
            return "break"
        if evento.char and evento.char.isprintable():
            return "break"  #ignora letras e separadores digitados manualmente
        return None

    def corrigir_colagem(evento=None):
        #permite colar 06112026 ou 06/11/2026 sem atrapalhar o cursor
        texto = campo.get()
        cursor = campo.index(tk.INSERT)
        antes = sum(c.isdigit() for c in texto[:cursor])
        numeros = so_numeros(texto)
        if texto != montar(numeros):
            aplicar(numeros, antes)

    campo.bind("<KeyPress>", ao_digitar, add="+")
    campo.bind("<<Paste>>", lambda evento: campo.after_idle(corrigir_colagem), add="+")
    campo.bind("<FocusOut>", corrigir_colagem, add="+")
    corrigir_colagem()
    return campo


def fundo_campo(canvas, x, y, largura, altura):
    def desenhar(x, y, largura, altura, cor):
        raio = min(16, altura // 2)
        canvas.create_oval(x, y, x + 2 * raio, y + altura, fill=cor, outline="")
        canvas.create_oval(x + largura - 2 * raio, y, x + largura, y + altura,
                           fill=cor, outline="")
        canvas.create_rectangle(x + raio, y, x + largura - raio, y + altura,
                                fill=cor, outline="")

    desenhar(x, y, largura, altura, "#D5B8B1") #a borda deixa o campo mais visível
    desenhar(x + 2, y + 2, largura - 4, altura - 4, "#FFF7F3")

def compartilhar_habilidade():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta para compartilhar uma habilidade.")
        return
    conta_que_abriu = usuario_logado["id"]
    nome_que_abriu = usuario_logado["usuario"]
    janela_Habilidade = tk.Toplevel(janela) #abre outra janela sem fechar a inicial
    janela_Habilidade.title("Bloomie - Compartilhar Habilidade")
    janela_Habilidade.geometry("1000x700")
    janela_Habilidade.resizable(False, False)

    imagem_habilidade = carregar_fundo("fundo_bloomie_funcionalidades.gif", 1000, 700)

    janela_Habilidade.imagem_habilidade = imagem_habilidade

    fundo_habilidade = tk.Canvas(
        janela_Habilidade,
        width=1000,
        height=700,
        highlightthickness=0,
        borderwidth=0
    )

    fundo_habilidade.pack()

    fundo_habilidade.create_image(
        0, 0,
        image=imagem_habilidade,
        anchor="nw"
    ) #coloca a imagem de fundo dentro do canvas

    fundo_habilidade.create_text(
        482, 150,
        text="Bloomie",
        font=("Arial", 27, "bold"),
        fill="#713D4D"
    )
    for desloc_x, desloc_y in ((0, -8), (8, -2), (5, 7), (-5, 7), (-8, -2)):
        fundo_habilidade.create_oval(
            579 + desloc_x - 6, 150 + desloc_y - 6,
            579 + desloc_x + 6, 150 + desloc_y + 6,
            fill="#B98591", outline=""
        )
    fundo_habilidade.create_oval(
        576, 147, 582, 153, fill="#FFF7F3", outline=""
    )

    fundo_habilidade.create_text(
        500, 235,
        text="🌿 Compartilhe sua habilidade",
        font=("Arial", 20, "bold"),
        fill="#4F5D4D"
    )

    fundo_habilidade.create_text(
        500, 265,
        text=f"salvando para @{nome_que_abriu}", font=("Arial", 10), fill="#713D4D"
    )

    fundo_habilidade.create_text(
        500, 290,
        text="Habilidade:",
        font=("Arial", 11),
        fill="#333333"
    )

    fundo_campo(fundo_habilidade, 350, 305, 300, 43)

    entrada_habilidade = tk.Entry(
        janela_Habilidade,
        font=("Arial", 11),
        width=30,
        justify="center",
        bg="#FFF7F3", fg="#594C50", relief="flat", bd=0
    )

    entrada_habilidade.place(
        x=367,
        y=310,
        width=266, height=34
    )

    fundo_habilidade.create_text(
        500, 375,
        text="Categoria:",
        font=("Arial", 11),
        fill="#333333"
    )

    fundo_campo(fundo_habilidade, 350, 390, 300, 43)

    entrada_categoria = tk.Entry(
        janela_Habilidade,
        font=("Arial", 11),
        width=30,
        justify="center",
        bg="#FFF7F3", fg="#594C50", relief="flat", bd=0
    )

    entrada_categoria.place(
        x=367,
        y=395,
        width=266, height=34
    )

    fundo_habilidade.create_text(
        500, 460,
        text="Descrição:",
        font=("Arial", 11),
        fill="#333333"
    )

    fundo_campo(fundo_habilidade, 350, 475, 300, 84)

    entrada_descricao = tk.Text(
        janela_Habilidade,
        font=("Arial", 11),
        width=30,
        height=4,
        bg="#FFF7F3", fg="#594C50", relief="flat", bd=0
    )

    entrada_descricao.place(
        x=366,
        y=483, width=268, height=64
    )

    texto_resultado = fundo_habilidade.create_text(
        500, 574,
        text="",
        font=("Arial", 10),
        fill="red"
    )


    def salvar_habilidade():
        if usuario_logado is None or usuario_logado["id"] != conta_que_abriu:
            messagebox.showwarning("Bloomie", "A conta mudou. Abra Compartilhar novamente.", parent=janela_Habilidade)
            return
        habilidade = entrada_habilidade.get()
        categoria = entrada_categoria.get()
        descricao = entrada_descricao.get("1.0", "end").strip()

        if habilidade == "" or categoria == "":
            fundo_habilidade.itemconfig(
                texto_resultado,
                text="Preencha a habilidade e a categoria.",
                fill="red"
            )
            return

        cursor.execute(
            """INSERT INTO habilidades
            (usuario_id, habilidade, categoria, descricao)
            VALUES (?, ?, ?, ?)""",
            (
                conta_que_abriu,
                habilidade,
                categoria,
                descricao
            )
        )

        conexao.commit()
        ganhou = dar_recompensa(usuario_logado["id"], "primeira_habilidade", 5)
        if ganhou:
            messagebox.showinfo("Missões Bloomie 🌸", "Sua primeira habilidade rendeu 5 BloomCoins!", parent=janela_Habilidade)

        fundo_habilidade.itemconfig(
            texto_resultado,
            text="Habilidade compartilhada com sucesso! 🌿",
            fill="green"
        )

        entrada_habilidade.delete(0, "end")
        entrada_categoria.delete(0, "end")
        entrada_descricao.delete("1.0", "end")


    botao_compartilhar = botao_suave(
        janela_Habilidade, "Compartilhar", salvar_habilidade,
        largura=190, altura=40, cor="#89998B"
    )
    botao_compartilhar.place(x=405, y=608)

    #pro enter avançar e também salvar a descrição 
    entrada_habilidade.bind("<Return>", lambda event: entrada_categoria.focus_set())
    entrada_categoria.bind("<Return>", lambda event: entrada_descricao.focus_set())
    entrada_descricao.bind("<Control-Return>", lambda event: (salvar_habilidade(), "break")[1])
    entrada_habilidade.focus_set()


def abrir_minhas_habilidades():
    janela_Minhas_Habilidades = tk.Toplevel(janela) 
    janela_Minhas_Habilidades.title("Bloomie - Minhas Habilidades")
    janela_Minhas_Habilidades.geometry("1000x700")
    janela_Minhas_Habilidades.resizable(False, False)

    imagem_minhas_habilidades = carregar_fundo("fundo_bloomie_funcionalidades.gif", 1000, 700)

    janela_Minhas_Habilidades.imagem_minhas_habilidades = imagem_minhas_habilidades

    fundo_minhas_habilidades = tk.Canvas(
        janela_Minhas_Habilidades,
        width=1000,
        height=700,
        highlightthickness=0,
        borderwidth=0
    )

    fundo_minhas_habilidades.pack()

    fundo_minhas_habilidades.create_image(
        0, 0,
        image=imagem_minhas_habilidades,
        anchor="nw"
    ) 

    fundo_minhas_habilidades.create_text(
        482, 150,
        text="Bloomie",
        font=("Arial", 27, "bold"),
        fill="#713D4D"
    )
    for desloc_x, desloc_y in ((0, -8), (8, -2), (5, 7), (-5, 7), (-8, -2)):
        fundo_minhas_habilidades.create_oval(
            579 + desloc_x - 6, 150 + desloc_y - 6,
            579 + desloc_x + 6, 150 + desloc_y + 6,
            fill="#B98591", outline=""
        )
    fundo_minhas_habilidades.create_oval(
        576, 147, 582, 153, fill="#FFF7F3", outline=""
    )

    fundo_minhas_habilidades.create_text(
        500, 235,
        text="🌿 Minhas Habilidades",
        font=("Arial", 20, "bold"),
        fill="#4F5D4D"
    )
    fundo_minhas_habilidades.create_text(
        500, 271,
        text=f"habilidades de @{usuario_logado['usuario']}",
        font=("Arial", 10), fill="#713D4D"
    )

    cursor.execute(
        "SELECT id, habilidade, categoria, descricao FROM habilidades WHERE usuario_id = ?",
        (usuario_logado["id"],)
    )

    habilidades = cursor.fetchall()

    fundo_campo(fundo_minhas_habilidades, 280, 290, 440, 250)

    lista_habilidades = tk.Listbox(
        janela_Minhas_Habilidades,
        font=("Arial", 11),
        width=50,
        height=15,
        bg="#FFF7F3", fg="#594C50", relief="flat", bd=0,
        selectbackground="#D5A7B1", highlightthickness=0
    ) #listbox cria uma caixa que mostra uma lista de itens na tela

    lista_habilidades.place(
        x=301,
        y=308, width=399, height=220
    )

    if not habilidades:
        lista_habilidades.insert(
            tk.END,
            "Você ainda não compartilhou nenhuma habilidade."
        )

    else:
        for habilidade in habilidades:
            lista_habilidades.insert(
                tk.END,
                f"{habilidade[1]} - {habilidade[2]}"
            ) #tk.end coloca o novo item no final da lista

    botao_editar = botao_suave(
        janela_Minhas_Habilidades, "✏️ Editar",
        lambda: editar_habilidade(lista_habilidades, habilidades, janela_Minhas_Habilidades)
    )
    botao_editar.place(x=295, y=567)

    botao_excluir = botao_suave(
        janela_Minhas_Habilidades, "Excluir",
        lambda: excluir_habilidade(lista_habilidades, habilidades, janela_Minhas_Habilidades)
    )
    botao_excluir.place(x=505, y=567)

    #pro enter editar a habilidade selecionada
    lista_habilidades.bind(
        "<Return>",
        lambda event: editar_habilidade(lista_habilidades, habilidades, janela_Minhas_Habilidades)
    )


def editar_habilidade(lista_habilidades, habilidades, janela_Minhas_Habilidades):

    if not habilidades:
        messagebox.showwarning(
            "Aviso",
            "Você ainda não possui habilidades cadastradas.",
            parent=janela_Minhas_Habilidades
        )

        janela_Minhas_Habilidades.lift()
        return

    indice_selecionado = lista_habilidades.curselection()

    if not indice_selecionado:
        messagebox.showwarning(
            "Aviso",
            "Selecione uma habilidade para editar.",
            parent=janela_Minhas_Habilidades
        )

        janela_Minhas_Habilidades.lift()
        return

    indice = indice_selecionado[0]

    habilidade_id, habilidade_nome, categoria, descricao = habilidades[indice]

    janela_Editar = tk.Toplevel(janela_Minhas_Habilidades)
    janela_Editar.title("Bloomie - Editar Habilidade")
    janela_Editar.geometry("400x300")
    janela_Editar.resizable(False, False)
    janela_Editar.configure(bg="#F8E9E6")
    aplicar_fundo_funcionalidades(janela_Editar, 400, 300)

    tk.Label(
        janela_Editar,
        text="Habilidade:",
        font=("Arial", 11), bg="#F8E9E6", fg="#713D4D"
    ).pack(pady=5)

    entrada_habilidade = tk.Entry(
        janela_Editar,
        font=("Arial", 11),
        width=30, bg="#FFF7F3", fg="#594C50", relief="flat", bd=0,
        highlightthickness=2, highlightbackground="#D5B8B1",
        highlightcolor="#89998B"
    )

    entrada_habilidade.pack(pady=5)
    entrada_habilidade.insert(0, habilidade_nome)

    tk.Label(
        janela_Editar,
        text="Categoria:",
        font=("Arial", 11), bg="#F8E9E6", fg="#713D4D"
    ).pack(pady=5)

    entrada_categoria = tk.Entry(
        janela_Editar,
        font=("Arial", 11),
        width=30, bg="#FFF7F3", fg="#594C50", relief="flat", bd=0,
        highlightthickness=2, highlightbackground="#D5B8B1",
        highlightcolor="#89998B"
    )

    entrada_categoria.pack(pady=5)
    entrada_categoria.insert(0, categoria)

    tk.Label(
        janela_Editar,
        text="Descrição:",
        font=("Arial", 11), bg="#F8E9E6", fg="#713D4D"
    ).pack(pady=5)

    entrada_descricao = tk.Text(
        janela_Editar,
        font=("Arial", 11),
        width=30,
        height=4, bg="#FFF7F3", fg="#594C50", relief="flat", bd=0,
        highlightthickness=2, highlightbackground="#D5B8B1",
        highlightcolor="#89998B"
    )

    entrada_descricao.pack(pady=5)

    if descricao:
        entrada_descricao.insert("1.0", descricao)


    def salvar_edicao():
        nova_habilidade = entrada_habilidade.get()
        nova_categoria = entrada_categoria.get()
        nova_descricao = entrada_descricao.get("1.0", "end").strip()

        if not nova_habilidade or not nova_categoria:
            messagebox.showwarning(
                "Aviso",
                "Preencha a habilidade e a categoria.",
                parent=janela_Editar
            )
            return

        cursor.execute(
            """UPDATE habilidades
            SET habilidade = ?, categoria = ?, descricao = ?
            WHERE id = ?""",
            (
                nova_habilidade,
                nova_categoria,
                nova_descricao,
                habilidade_id
            )
        ) #atualiza a habilidade no banco

        conexao.commit()

        lista_habilidades.delete(indice)

        lista_habilidades.insert(
            indice,
            f"{nova_habilidade} - {nova_categoria}"
        )

        habilidades[indice] = (
            habilidade_id,
            nova_habilidade,
            nova_categoria,
            nova_descricao
        )

        messagebox.showinfo(
            "Bloomie",
            "Habilidade editada com sucesso!",
            parent=janela_Editar
        )

        janela_Editar.destroy()


    botao_salvar = botao_suave(janela_Editar, "Salvar", salvar_edicao)
    botao_salvar.pack(pady=10)

    entrada_habilidade.bind("<Return>", lambda event: entrada_categoria.focus_set())
    entrada_categoria.bind("<Return>", lambda event: entrada_descricao.focus_set())
    entrada_descricao.bind("<Control-Return>", lambda event: (salvar_edicao(), "break")[1])
    entrada_habilidade.focus_set()


def excluir_habilidade(lista_habilidades, habilidades, janela_Minhas_Habilidades):

    if not habilidades:
        messagebox.showwarning(
            "Aviso",
            "Você ainda não possui habilidades cadastradas.",
            parent=janela_Minhas_Habilidades
        )

        janela_Minhas_Habilidades.lift()
        return

    indice_selecionado = lista_habilidades.curselection()

    if not indice_selecionado:
        messagebox.showwarning(
            "Aviso",
            "Selecione uma habilidade para excluir.",
            parent=janela_Minhas_Habilidades
        )

        janela_Minhas_Habilidades.lift()
        return

    indice = indice_selecionado[0]

    habilidade_id, _, _, _ = habilidades[indice]

    confirmacao = messagebox.askyesno(
        "Confirmação",
        "Tem certeza que deseja excluir esta habilidade?",
        parent=janela_Minhas_Habilidades
    )

    if confirmacao:
        cursor.execute(
            "SELECT COUNT(*) FROM solicitacoes WHERE habilidade_id = ? AND status IN ('pendente', 'aceita')",
            (habilidade_id,)
        )
        if cursor.fetchone()[0] > 0:
            messagebox.showwarning(
                "Bloomie", "Essa habilidade tem solicitações abertas. Resolva os pedidos antes de excluí-la.",
                parent=janela_Minhas_Habilidades
            )
            return
        cursor.execute(
            "DELETE FROM interesses_habilidades WHERE habilidade_id = ?", (habilidade_id,)
        )
        cursor.execute(
            "DELETE FROM bloommatch_reacoes WHERE habilidade_id = ?", (habilidade_id,)
        )
        cursor.execute(
            "DELETE FROM habilidades WHERE id = ?",
            (habilidade_id,)
        ) #exclui a habilidade do banco

        conexao.commit()

        lista_habilidades.delete(indice)
        habilidades.pop(indice)

        messagebox.showinfo(
            "Bloomie",
            "Habilidade excluída com sucesso!",
            parent=janela_Minhas_Habilidades
        )

        if not habilidades:
            lista_habilidades.insert(
                tk.END,
                "Você ainda não compartilhou nenhuma habilidade."
            )




def mostrar_perfil_alheio(pessoa_id, parent=None):
    if usuario_logado is None:
        return
    cursor.execute("""
        SELECT u.nome, u.usuario, p.sobre_mim, p.cidade, p.quero_aprender,
               p.frase, p.interesses, p.disponibilidade, p.forma_aprender, p.foto
        FROM usuarios u LEFT JOIN perfis p ON p.usuario_id = u.id
        WHERE u.id = ? AND u.id != ?
    """, (pessoa_id, usuario_logado["id"]))
    dados = cursor.fetchone()
    if not dados:
        messagebox.showinfo("Bloomie", "Esse perfil não está disponível.", parent=parent or janela)
        return
    nome, usuario, sobre, cidade, aprender, frase, interesses, disponibilidade, forma, foto = dados
    cursor.execute(
        "SELECT habilidade, categoria, COALESCE(descricao, '') FROM habilidades "
        "WHERE usuario_id = ? ORDER BY habilidade COLLATE NOCASE", (pessoa_id,)
    )
    habilidades = cursor.fetchall()

    perfil = tk.Toplevel(parent or janela)
    perfil.title(f"Bloomie - Perfil de {nome}")
    perfil.geometry("830x690")
    perfil.resizable(False, False)

    tela = tk.Canvas(perfil, width=830, height=690, bg="#F8E8F0", highlightthickness=0)
    tela.pack(fill="both", expand=True)
    try:
        imagem = tk.PhotoImage(file=os.path.join(PASTA_PROJETO, "fundo_bloomie_funcionalidades.gif"))
        perfil.fundo_perfil_visitado = imagem
        tela.create_image(0, 0, image=imagem, anchor="nw")
    except (tk.TclError, OSError):
        pass

    rosa = "#BC838D"
    escuro = "#713D4D"
    cartao = "#F8E9E6"
    borda = "#D5B8B1"
    texto = "#594C50"
    claro = "#FFF7F3"

    def arredondado(x, y, largura, altura, cor, tag=None):
        raio = min(24, largura // 2, altura // 2)
        opcoes = {"fill": cor, "outline": "", "tags": tag}
        tela.create_oval(x, y, x + 2 * raio, y + 2 * raio, **opcoes)
        tela.create_oval(x + largura - 2 * raio, y, x + largura, y + 2 * raio, **opcoes)
        tela.create_oval(x, y + altura - 2 * raio, x + 2 * raio, y + altura, **opcoes)
        tela.create_oval(x + largura - 2 * raio, y + altura - 2 * raio, x + largura, y + altura, **opcoes)
        tela.create_rectangle(x + raio, y, x + largura - raio, y + altura, **opcoes)
        tela.create_rectangle(x, y + raio, x + largura, y + altura - raio, **opcoes)

    arredondado(36, 34, 758, 620, borda)
    arredondado(38, 36, 754, 616, cartao)
    tela.create_text(78, 72, text=f"Perfil de {nome} 🌸", font=("Arial", 24, "bold"), fill=escuro, anchor="nw")
    tela.create_text(81, 116, text="@" + usuario, font=("Arial", 13), fill="#89998B", anchor="nw")

    if foto:
        caminho = foto if os.path.isabs(foto) else os.path.join(PASTA_PROJETO, foto)
        if os.path.isfile(caminho):
            try:
                with Image.open(caminho) as original:
                    imagem = ImageOps.fit(original.convert("RGBA"), (110, 110))
                mascara = Image.new("L", (110, 110), 0)
                ImageDraw.Draw(mascara).ellipse((0, 0, 109, 109), fill=255)
                imagem.putalpha(mascara)
                perfil.foto_visitada = ImageTk.PhotoImage(imagem)
                tela.create_image(685, 93, image=perfil.foto_visitada, anchor="center")
            except (OSError, ValueError, tk.TclError):
                pass

    bloco = tk.Text(
        perfil, font=("Arial", 11), bg=cartao, fg=texto,
        wrap="word", relief="flat", padx=20, pady=18, cursor="arrow"
    )
    bloco.place(x=78, y=152, width=642, height=410)
    campos = (
        ("Frase", frase), ("Cidade", cidade), ("Sobre mim", sobre),
        ("Quer aprender", aprender), ("Interesses", interesses),
        ("Disponibilidade", disponibilidade), ("Forma de aprender", forma)
    )
    for titulo, valor in campos:
        bloco.insert("end", f"{titulo}:  {valor or 'Não informado'}\n\n")
    bloco.insert("end", "Habilidades que ensina:\n")
    if habilidades:
        for habilidade, categoria, descricao in habilidades:
            bloco.insert("end", f"  • {habilidade} ({categoria})" + (f" — {descricao}" if descricao else "") + "\n")
    else:
        bloco.insert("end", "  Nenhuma habilidade publicada por enquanto.\n")
    bloco.configure(state="disabled")

    #fundo do texto pra combinar com o restante da tela
    arredondado(74, 148, 650, 418, borda)
    arredondado(76, 150, 646, 414, cartao)
    tela.tag_lower("all")
    try:
        tela.create_image(0, 0, image=perfil.fundo_perfil_visitado, anchor="nw")
    except Exception:
        pass
    #redesenha o cartão depois do fundo
    tela.delete("all")
    try:
        tela.create_image(0, 0, image=perfil.fundo_perfil_visitado, anchor="nw")
    except Exception:
        pass
    arredondado(36, 34, 758, 620, borda)
    arredondado(38, 36, 754, 616, cartao)
    tela.create_text(78, 72, text=f"Perfil de {nome} 🌸", font=("Arial", 24, "bold"), fill=escuro, anchor="nw")
    tela.create_text(81, 116, text="@" + usuario, font=("Arial", 13), fill="#89998B", anchor="nw")
    arredondado(74, 148, 650, 418, borda)
    arredondado(76, 150, 646, 414, cartao)
    if getattr(perfil, "foto_visitada", None):
        tela.create_image(685, 93, image=perfil.foto_visitada, anchor="center")

    botao_suave(perfil, "Pedir aula", lambda: escolher_aula_com_pessoa(pessoa_id, perfil), largura=190, cor="#89998B").place(x=90, y=602)
    botao_suave(perfil, "Oferecer aula", lambda: oferecer_aula_para_pessoa(pessoa_id, perfil), largura=190).place(x=320, y=602)
    botao_suave(perfil, "Voltar", perfil.destroy, largura=175, cor="#B69B89").place(x=560, y=602)

def abrir_perfis_alheios(parent=None):
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return
    pai = parent if parent is not None else janela
    janela_perfis = tk.Toplevel(pai)
    if parent is not None:
        janela_perfis.transient(parent)
    janela_perfis.title("Bloomie - Ver outros perfis")
    janela_perfis.geometry("860x620")
    janela_perfis.resizable(False, False)

    tela = tk.Canvas(janela_perfis, width=860, height=620, bg="#FFF7F3", highlightthickness=0, bd=0)
    tela.pack()
    try:
        img = carregar_fundo("fundo_bloomie_funcionalidades.gif", 860, 620)
        janela_perfis.fundo_perfis = img
        tela.create_image(0, 0, image=img, anchor="nw")
    except Exception:
        pass

    tela.create_text(430, 42, text="Conheça outros perfis 🌸", font=("Arial", 24, "bold"), fill="#713D4D")
    tela.create_text(430, 80, text="Visite perfis, conheça habilidades e escolha aprender ou ensinar.",
                     fill="#594C50", font=("Arial", 11))

    fundo_campo(tela, 48, 110, 750, 40)
    busca = tk.Entry(janela_perfis, font=("Arial", 12), bg="#FFF7F3", fg="#594C50", relief="flat", bd=0)
    busca.place(x=64, y=117, width=718, height=26)

    colunas = ("nome", "usuario", "cidade", "habilidades")
    lista = ttk.Treeview(janela_perfis, columns=colunas, show="headings", selectmode="browse")
    for campo, titulo, largura in (
        ("nome", "Nome", 160), ("usuario", "Usuário", 155),
        ("cidade", "Cidade", 165), ("habilidades", "Habilidades que ensina", 266)
    ):
        lista.heading(campo, text=titulo)
        lista.column(campo, width=largura, anchor="center")
    lista.place(x=48, y=175, width=736, height=313)
    barra = ttk.Scrollbar(janela_perfis, orient="vertical", command=lista.yview)
    barra.place(x=784, y=175, height=313)
    lista.configure(yscrollcommand=barra.set)

    def atualizar(evento=None):
        filtro = busca.get().casefold().strip()
        for item in lista.get_children():
            lista.delete(item)
        cursor.execute("""
            SELECT u.id, u.nome, u.usuario, COALESCE(p.cidade, ''),
                   COALESCE(GROUP_CONCAT(h.habilidade, ', '), '')
            FROM usuarios u
            LEFT JOIN perfis p ON p.usuario_id = u.id
            LEFT JOIN habilidades h ON h.usuario_id = u.id
            WHERE u.id != ?
            GROUP BY u.id, u.nome, u.usuario, p.cidade
            ORDER BY u.nome COLLATE NOCASE
        """, (usuario_logado["id"],))
        for pessoa_id, nome, user, cidade, habilidades in cursor.fetchall():
            if filtro and filtro not in f"{nome} {user} {cidade} {habilidades}".casefold():
                continue
            lista.insert("", "end", iid=str(pessoa_id),
                         values=(nome, "@" + user, cidade or "Não informada", habilidades or "—"))

    def visitar():
        escolha = lista.selection()
        if not escolha:
            messagebox.showinfo("Bloomie", "Selecione um perfil primeiro.", parent=janela_perfis)
            return
        mostrar_perfil_alheio(int(escolha[0]), janela_perfis)

    def criar_btn(x, y, larg, texto, cor, tag, cmd):
        alt, r = 40, 20
        tela.create_oval(x, y, x + 2*r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_oval(x + larg - 2*r, y, x + larg, y + alt, fill=cor, outline="", tags=tag)
        tela.create_rectangle(x + r, y, x + larg - r, y + alt, fill=cor, outline="", tags=tag)
        tela.create_text(x + larg/2, y + alt/2, text=texto, font=("Arial", 11, "bold"), fill="white", tags=tag)
        tela.tag_bind(tag, "<Button-1>", lambda e: cmd())
        tela.tag_bind(tag, "<Enter>", lambda e: tela.config(cursor="hand2"))
        tela.tag_bind(tag, "<Leave>", lambda e: tela.config(cursor=""))

    busca.bind("<KeyRelease>", atualizar)
    janela_perfis.bind("<FocusIn>", lambda evento: atualizar() if evento.widget is janela_perfis else None)
    busca.bind("<Return>", lambda evento: (visitar(), "break")[1])
    lista.bind("<Double-1>", lambda evento: visitar())

    criar_btn(110, 527, 190, "Ver perfil", "#89998B", "btn_ver_p", visitar)
    criar_btn(339, 527, 190, "Atualizar", "#B98591", "btn_att_p", atualizar)
    criar_btn(568, 527, 190, "Voltar", "#B69B89", "btn_vol_p", janela_perfis.destroy)

    atualizar()
    busca.focus_set()

def abrir_explorar_habilidades():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    janela_Explorar = tk.Toplevel(janela)
    janela_Explorar.title("Bloomie - Explorar Habilidades")
    janela_Explorar.geometry("1300x800")
    janela_Explorar.resizable(False, False)

    tela_explorar = tk.Canvas(
        janela_Explorar, width=1300,
        height=800,
        bg="#F8E8F0",
        highlightthickness=0,
        borderwidth=0
    )
    tela_explorar.pack()

    caminho_fundo = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "fundo_bloomie_funcionalidades.gif"
    )

    try:
        imagem_explorar = tk.PhotoImage(file=caminho_fundo)
        janela_Explorar.imagem_explorar = imagem_explorar
        tela_explorar.create_image(0, 0, image=imagem_explorar, anchor="nw")
    except (tk.TclError, OSError) as erro:
        print("Não foi possível carregar o fundo do Explorar:", erro)

    rosa = "#BC838D"
    rosa_escuro = "#713D4D"
    rosa_claro = "#F0D6D7"
    cor_cartao = "#F8E9E6"
    cor_campo = "#FFF5F2"
    cor_texto = "#594C50"

    def arredondado(x, y, largura, altura, raio, cor, tag=None):
        opcoes= {"fill": cor, "outline": "", "tags": tag}

        tela_explorar.create_oval(
            x, y, x + raio * 2, y + raio * 2, **opcoes
        )

        tela_explorar.create_oval(
            x + largura - raio * 2, y,
            x + largura, y + raio * 2, **opcoes
        )

        tela_explorar.create_oval(
            x, y + altura - raio * 2,
            x + raio * 2, y + altura, **opcoes
        )

        tela_explorar.create_oval(
            x + largura - raio * 2,
            y + altura - raio * 2,
            x + largura, y + altura, **opcoes
        )

        tela_explorar.create_rectangle(
            x + raio, y,
            x + largura - raio, y + altura, **opcoes
        )

        tela_explorar.create_rectangle(
            x, y + raio,
            x + largura, y + altura - raio, **opcoes
        )

    def escrever(x, y, texto, tamanho=11, negrito=False, tag=None):
        tela_explorar.create_text(
            x, y,
            text=texto,
            font=("Arial", tamanho, "bold" if negrito else "normal"),
            fill=rosa_escuro,
            anchor="nw",
            tags=tag
        )

    def criar_botao(x, y, largura, texto, comando, tag):
        tags = (tag, "resultados") if tag.startswith(("perfil_", "interesse_", "aula_")) else tag
        arredondado(x, y, largura, 36, 16, rosa, tags)

        tela_explorar.create_text(
            x + largura / 2,
            y + 18,
            text=texto,
            font=("Arial", 10, "bold"),
            fill="white",
            tags=tags
        )

        tela_explorar.tag_bind(
            tag,
            "<Button-1>",
            lambda event: comando()
        )

    escrever(30, 32, "Bloomie 🌸", 25, True)

    tela_explorar.create_line(
        24, 660, 224, 660,
        fill="#D6B6B5"
    )

    def botao_menu(texto, y, comando, tag, ativo=False):
        if ativo:
            arredondado(
                14, y - 7, 217, 42, 15, rosa_claro, tag
            )

        escrever(34, y + 5, texto, 11, ativo, tag)

        tela_explorar.tag_bind(
            tag,
            "<Button-1>",
            lambda event: comando()
        )

    botao_menu(
        "⌂  Início", 119,
        janela_Explorar.destroy, "explorar_inicio"
    )

    botao_menu(
        "⌕  Explorar", 170,
        lambda: None, "explorar_atual", True
    )

    botao_menu(
        "⊕  Compartilhar", 272,
        compartilhar_habilidade, "explorar_compartilhar"
    )

    botao_menu(
        "☷  Minhas habilidades", 323,
        abrir_minhas_habilidades, "explorar_minhas"
    )

    botao_menu(
        "♙  Meu perfil", 374,
        abrir_meu_perfil, "explorar_perfil"
    )

    botao_menu(
        "❀  Jardim de Conquistas", 425,
        abrir_jardim_conquistas, "explorar_jardim"
    )

    botao_menu(
        "◷  Histórico de trocas", 476,
        abrir_historico_trocas, "explorar_historico"
    )

    botao_menu(
        "✦  Missões Bloomie", 527,
        abrir_missoes_bloomie, "explorar_missoes"
    )

    botao_menu(
        "✉  Solicitações", 578, abrir_solicitacoes, "explorar_pedidos"
    )

    botao_menu(
        "⚙  Configurações", 683,
        abrir_configuracoes, "explorar_config"
    )

    botao_menu(
        "↪  Voltar", 732,
        janela_Explorar.destroy, "explorar_voltar"
    )

    escrever(320, 42, "Explorar Habilidades ✦", 27, True)
    escrever(322, 88, "Encontre pessoas para aprender algo novo.", 12)

    arredondado(318, 145, 550, 49, 24, "#D5B8B1")
    arredondado(320, 147, 546, 45, 22, cor_campo)

    entrada_pesquisa = tk.Entry(
        janela_Explorar,
        font=("Arial", 12),
        bg=cor_campo,
        fg=cor_texto,
        relief="flat",
        bd=0
    )

    entrada_pesquisa.place(
        x=340, y=156,
        width=505, height=26
    )

    categorias = ["Todas as categorias"]
    categoria_atual = tk.StringVar(value=categorias[0])

    cursor.execute(
        "SELECT DISTINCT categoria FROM habilidades ORDER BY categoria"
    )

    for linha in cursor.fetchall():
        if linha[0]:
            categorias.append(linha[0])

    categoria_menu = tk.OptionMenu(
        janela_Explorar,
        categoria_atual,
        *categorias
    )

    categoria_menu.config(
        font=("Arial", 11),
        bg="#89998B",
        fg="white",
        activebackground="#718575",
        activeforeground="white",
        relief="flat",
        borderwidth=0,
        highlightthickness=0
    )
    categoria_menu["menu"].config(
        bg="#FFF7F3", fg="#713D4D",
        activebackground="#F0DDE0", activeforeground="#713D4D",
        relief="flat", borderwidth=0
    )

    arredondado(895, 145, 367, 49, 23, "#D5B8B1")
    categoria_menu.place(
        x=897, y=147,
        width=363, height=45
    )

    escrever(322, 225, "Habilidades disponíveis", 17, True)

    pagina_atual = [0]
    resultados = []

    def ver_perfil(usuario_id):
        #a mesma tela de perfil é usada no explorar e no catálogo
        mostrar_perfil_alheio(usuario_id, janela_Explorar)

    def demonstrar_interesse(habilidade_id, dono_id):
        if dono_id == usuario_logado["id"]:
            messagebox.showinfo(
                "Bloomie",
                "Essa habilidade já é sua!",
                parent=janela_Explorar
            )
            return

        try:
            cursor.execute(
                """INSERT INTO interesses_habilidades
                   (usuario_id, habilidade_id)
                   VALUES (?, ?)""",
                (usuario_logado["id"], habilidade_id)
            )

            conexao.commit()

            messagebox.showinfo(
                "Bloomie 🌸",
                "Interesse registrado com sucesso!",
                parent=janela_Explorar
            )

        except sqlite3.IntegrityError:
            messagebox.showinfo(
                "Bloomie",
                "Você já demonstrou interesse nessa habilidade.",
                parent=janela_Explorar
            )

    def mostrar_resultados():
        tela_explorar.delete("resultados")
        resultados.clear()

        pesquisa = entrada_pesquisa.get().strip()
        categoria = categoria_atual.get()

        consulta = """
            SELECT habilidades.id, habilidades.habilidade,
                   habilidades.categoria, habilidades.descricao,
                   usuarios.id, usuarios.usuario
            FROM habilidades
            JOIN usuarios
            ON habilidades.usuario_id = usuarios.id
            WHERE habilidades.habilidade LIKE ?
        """

        parametros = ["%" + pesquisa + "%"]

        if categoria != "Todas as categorias":
            consulta += " AND habilidades.categoria = ?"
            parametros.append(categoria)

        consulta += " ORDER BY habilidades.id DESC"

        cursor.execute(consulta, parametros)

        resultados.extend(cursor.fetchall())

        total_paginas = max(1, (len(resultados) + 3) // 4)
        pagina_atual[0] = min(pagina_atual[0], total_paginas -1)

        inicio = pagina_atual[0] * 4
        habilidades_pagina = resultados[inicio:inicio + 4]

        posicoes = [
            (320, 275),
            (805, 275),
            (320, 480),
            (805, 480)
        ]

        if not habilidades_pagina:
            escrever(
                450, 370,
                "Nenhuma habilidade encontrada",
                16, True, "resultados"
            )
            return

        for indice, habilidade in enumerate(habilidades_pagina):
            habilidade_id, nome, categoria, descricao, dono_id, usuario = habilidade

            x, y= posicoes[indice]

            arredondado(
                x, y, 457, 190, 25,
                cor_cartao, "resultados"
            )


            tela_explorar.create_text(
                x + 22, y + 20,
                text=categoria,
                font=("Arial", 10),
                fill=rosa,
                anchor="nw",
                tags="resultados"
            )

            tela_explorar.create_text(
                x + 22, y + 47,
                text=nome,
                font=("Arial", 16, "bold"),
                fill=rosa_escuro,
                anchor="nw",
                width=410,
                tags="resultados"
            )

            tela_explorar.create_text(
                x + 22, y + 81,
                text="Por @" + usuario,
                font=("Arial", 10),
                fill=cor_texto,
                anchor="nw",
                tags="resultados"
            )

            descricao_curta = (descricao or "Sem descrição")[:100]

            tela_explorar.create_text(
                x + 22, y + 107,
                text=descricao_curta,
                font=("Arial", 10),
                fill=cor_texto,
                anchor="nw",
                width=410,
                tags="resultados"
            )

            criar_botao(
                x + 22, y + 148, 115,
                "Ver perfil",
                lambda id=dono_id: ver_perfil(id),
                f"perfil_{indice}"
            )

            criar_botao(
                x + 147, y + 148, 132,
                "Tenho interesse",
                lambda id=habilidade_id, dono=dono_id:
                    demonstrar_interesse(id, dono),
                f"interesse_{indice}"
            )
            criar_botao(
                x + 287, y + 148, 145,
                "Pedir aula",
                lambda id=habilidade_id: enviar_solicitacao_de_aula(id, janela_Explorar),
                f"aula_{indice}"
            )

        escrever(
            1020, 725,
            f"Página {pagina_atual[0] + 1} de {total_paginas}",
            11, False, "resultados"
        )

    def proxima_pagina():
        total_paginas = max(1, (len(resultados) + 3) // 4)

        if pagina_atual[0] + 1 < total_paginas:
            pagina_atual[0] += 1
            mostrar_resultados()

    def pagina_anterior():
        if pagina_atual[0] > 0:
            pagina_atual[0] -= 1
            mostrar_resultados()

    criar_botao(
        330, 715, 145,
        "← Anterior", pagina_anterior,
        "botao_anterior"
    )

    criar_botao(
        490, 715, 145,
        "Próxima →", proxima_pagina,
        "botao_proxima"
    )

    def nova_pesquisa(evento=None):
        pagina_atual[0] = 0
        mostrar_resultados()

    entrada_pesquisa.bind("<KeyRelease>", nova_pesquisa)
    entrada_pesquisa.bind("<Return>", nova_pesquisa)

    categoria_atual.trace_add(
        "write",
        lambda *args: nova_pesquisa()
    ) #atualiza a pesquisa quando a categoria mudar

    entrada_pesquisa.focus_set()
    mostrar_resultados()

def consultar_curtidas_recebidas(usuario_id):
    cursor.execute("""
        SELECT u.id, u.nome, u.usuario,
               GROUP_CONCAT(DISTINCT h.habilidade),
               EXISTS (
                   SELECT 1
                   FROM bloommatch_reacoes minha
                   JOIN habilidades outra ON outra.id = minha.habilidade_id
                   WHERE minha.usuario_id = ?
                     AND outra.usuario_id = u.id
                     AND minha.acao = 'curti'
               )
        FROM usuarios u
        JOIN bloommatch_reacoes r
          ON r.usuario_id = u.id AND r.acao = 'curti'
        JOIN habilidades h
          ON h.id = r.habilidade_id AND h.usuario_id = ?
        WHERE u.id != ?
        GROUP BY u.id, u.nome, u.usuario
        ORDER BY u.nome COLLATE NOCASE
    """, (usuario_id, usuario_id, usuario_id))
    return cursor.fetchall()


def listar_matches_para_agendamento(usuario_id):
    cursor.execute("""
        SELECT u.id, u.nome, u.usuario,
               GROUP_CONCAT(DISTINCT h.habilidade), MIN(h.id)
        FROM bloommatch_reacoes minha
        JOIN habilidades h ON h.id = minha.habilidade_id
        JOIN usuarios u ON u.id = h.usuario_id
        WHERE minha.usuario_id = ?
          AND minha.acao = 'curti'
          AND u.id != ?
          AND EXISTS (
              SELECT 1
              FROM bloommatch_reacoes curtida_recebida
              JOIN habilidades minha_habilidade
                ON minha_habilidade.id = curtida_recebida.habilidade_id
              WHERE curtida_recebida.usuario_id = u.id
                AND minha_habilidade.usuario_id = ?
                AND curtida_recebida.acao = 'curti'
          )
        GROUP BY u.id, u.nome, u.usuario
        ORDER BY u.nome COLLATE NOCASE
    """, (usuario_id, usuario_id, usuario_id))
    return cursor.fetchall()


def abrir_bloommatch():
    garantir_colunas_solicitacoes()
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return
    sincronizar_matches_em_pedidos(usuario_logado["id"])

    match = tk.Toplevel(janela)
    match.title("Bloomie - BloomMatch")
    match.geometry("1300x800")
    match.resizable(False, False)

    tela = tk.Canvas(
        match, width=1300, height=800,
        bg="#F8E8F0", highlightthickness=0
    )
    tela.pack()

    caminho = os.path.join(PASTA_PROJETO, "fundo_bloomie_funcionalidades.gif")
    try:
        fundo = tk.PhotoImage(file=caminho)
        match.fundo = fundo
        tela.create_image(0, 0, image=fundo, anchor="nw")
    except (tk.TclError, OSError):
        pass

    rosa = "#BC838D"
    escuro = "#713D4D"
    verde = "#89998B"
    creme = "#FFF7F3"
    texto_claro = "#6F6466"
    borda = "#E5D3D0"

    def arredondado(x, y, largura, altura, cor, tag=None):
        raio = min(25, altura // 2)
        opcoes = {"fill": cor, "outline": "", "tags": tag}
        tela.create_oval(x, y, x + 2 * raio, y + altura, **opcoes)
        tela.create_oval(
            x + largura - 2 * raio, y,
            x + largura, y + altura, **opcoes
        )
        tela.create_rectangle(
            x + raio, y, x + largura - raio, y + altura, **opcoes
        )

    def botao(x, y, largura, titulo, comando, tag, cor=rosa):
        arredondado(x, y, largura, 44, cor, tag)
        tela.create_text(
            x + largura / 2, y + 22,
            text=titulo, font=("Arial", 11, "bold"),
            fill="white", tags=tag
        )
        tela.tag_bind(tag, "<ButtonRelease-1>", lambda event: (comando(), "break")[1])
        tela.tag_bind(tag, "<Enter>", lambda event: tela.config(cursor="hand2"))
        tela.tag_bind(tag, "<Leave>", lambda event: tela.config(cursor=""))

    tela.create_text(
        30, 35, text="Bloomie 🌸",
        font=("Arial", 25, "bold"), fill=escuro, anchor="nw"
    )
    tela.create_text(
        315, 42, text="BloomMatch ♡",
        font=("Arial", 28, "bold"), fill=escuro, anchor="nw"
    )
    tela.create_text(
        315, 93, text=(f"@{usuario_logado['usuario']} · aqui aparecem habilidades de OUTRAS contas. "
                       "As suas ficam em Minhas habilidades."),
        font=("Arial", 12), fill=texto_claro, anchor="nw"
    )

    def atualizar_saldo():
        tela.delete("saldo_match")
        tela.create_text(
            1210, 58,
            text=f"🪙 {consultar_saldo(usuario_logado['id'])} BloomCoins",
            font=("Arial", 13, "bold"), fill=escuro,
            anchor="ne", tags="saldo_match"
        )

    atualizar_saldo()

    def carregar_sugestoes(incluir_vistos=False):
        cursor.execute(
            "SELECT quero_aprender FROM perfis WHERE usuario_id = ?",
            (usuario_logado["id"],)
        )
        perfil = cursor.fetchone()
        quero_aprender = (perfil[0] or "").casefold() if perfil else ""

        cursor.execute(
            "SELECT habilidade FROM habilidades WHERE usuario_id = ?",
            (usuario_logado["id"],)
        )
        minhas_habilidades = [
            linha[0].strip().casefold() for linha in cursor.fetchall()
        ]

        consulta = """
            SELECT h.id, u.id, u.nome, u.usuario, h.habilidade,
                   h.categoria, h.descricao, p.quero_aprender,
                   p.cidade, p.sobre_mim, p.foto, r.acao
            FROM habilidades h
            JOIN usuarios u ON h.usuario_id = u.id
            LEFT JOIN perfis p ON p.usuario_id = u.id
            LEFT JOIN bloommatch_reacoes r
                ON r.usuario_id = ? AND r.habilidade_id = h.id
            WHERE h.usuario_id != ?
        """
        if incluir_vistos:
            consulta += " AND r.habilidade_id IS NOT NULL"
        else:
            consulta += " AND r.habilidade_id IS NULL"
        consulta += " ORDER BY CASE r.acao WHEN 'curti' THEN 0 ELSE 1 END, h.id DESC"
        cursor.execute(consulta, (usuario_logado["id"], usuario_logado["id"]))

        encontrados = []
        for item in cursor.fetchall():
            (habilidade_id, professor_id, nome, usuario, habilidade,
             categoria, descricao, desejo, cidade, sobre, foto, acao_anterior) = item

            interesse = bool(
                quero_aprender and habilidade.strip().casefold() in quero_aprender
            )
            troca = any(
                nome_habilidade and nome_habilidade in (desejo or "").casefold()
                for nome_habilidade in minhas_habilidades
            )
            encontrados.append({
                "habilidade_id": habilidade_id,
                "professor_id": professor_id,
                "nome": nome,
                "usuario": usuario,
                "habilidade": habilidade,
                "categoria": categoria,
                "descricao": descricao or "Sem descrição cadastrada.",
                "quer_aprender": desejo or "Não informado",
                "cidade": cidade or "Cidade não informada",
                "sobre": sobre or "Ainda não escreveu sobre si.",
                "foto": foto or "",
                "interesse": interesse,
                "troca": troca,
                "acao_anterior": acao_anterior
            })

        #mostra primeiro as habilidades que combinam com o perfil
        encontrados.sort(key=lambda p: (not p["interesse"], not p["troca"]))
        return encontrados

    sugestoes = carregar_sugestoes()
    vendo_perfis_antigos = [False]
    atual = [0]
    inicio_arrasto = [None]
    ultimo_x = [None]
    foto_no_cartao = [None]

    def exibir_cartao():
        tela.delete("cartao")
        tela.delete("quantidade")
        foto_no_cartao[0] = None

        if atual[0] >= len(sugestoes) and not vendo_perfis_antigos[0]:
            revistos = carregar_sugestoes(incluir_vistos=True)
            if revistos:
                sugestoes[:] = revistos
                atual[0] = 0
                vendo_perfis_antigos[0] = True

        if atual[0] >= len(sugestoes):
            arredondado(350, 165, 875, 455, creme, "cartao")
            tela.create_text(
                790, 300, text="Você viu todos os perfis por agora 🌱",
                font=("Arial", 21, "bold"), fill=escuro, tags="cartao"
            )
            tela.create_text(
                790, 355,
                text="Use 'Rever perfis' para ver curtidas e perfis que você passou.",
                font=("Arial", 12), fill=texto_claro, tags="cartao"
            )
            tela.itemconfig("pular_match", state="hidden")
            tela.itemconfig("curtir_match", state="hidden")
            tela.itemconfig("pedir_match", state="hidden")
            tela.itemconfig("oferecer_match", state="hidden")
            tela.itemconfig("ver_perfil_cartao", state="hidden")
            return

        tela.itemconfig("ver_perfil_cartao", state="normal")
        tela.itemconfig("pular_match", state="normal")
        tela.itemconfig("curtir_match", state="normal")
        tela.itemconfig("pedir_match", state="normal")
        tela.itemconfig("oferecer_match", state="normal")

        pessoa = sugestoes[atual[0]]
        if pessoa["acao_anterior"]:
            estado = "Você já curtiu esta habilidade" if pessoa["acao_anterior"] == "curti" else "Você passou por esta habilidade"
            tela.create_text(
                790, 135, text=estado, font=("Arial", 10, "bold"),
                fill=escuro, tags="quantidade"
            )
        arredondado(355, 150, 870, 475, "#E9D5D3", "cartao")
        arredondado(360, 154, 860, 466, creme, "cartao")
        arredondado(386, 177, 808, 110, "#F1E0DD", "cartao")

        nome = pessoa["nome"]
        iniciais = "".join(parte[0] for parte in nome.split()[:2]).upper() or "B"
        tela.create_oval(
            422, 188, 509, 275,
            fill="#D6B7B8", outline="", tags="cartao"
        )
        foto = pessoa["foto"]
        if foto and not os.path.isabs(foto):
            foto = os.path.join(PASTA_PROJETO, foto)
        if foto and os.path.isfile(foto):
            try:
                with Image.open(foto) as arquivo_foto:
                    imagem = ImageOps.exif_transpose(arquivo_foto).convert("RGB")
                    imagem = ImageOps.fit(
                        imagem, (84, 84), method=Image.Resampling.LANCZOS
                    ).convert("RGBA")
                mascara_grande = Image.new("L", (336, 336), 0)
                ImageDraw.Draw(mascara_grande).ellipse((0, 0, 335, 335), fill=255)
                mascara = mascara_grande.resize((84, 84), Image.Resampling.LANCZOS)
                imagem.putalpha(mascara)
                foto_no_cartao[0] = ImageTk.PhotoImage(imagem)
                tela.create_image(
                    466, 232, image=foto_no_cartao[0], tags="cartao"
                )
            except (OSError, ValueError, tk.TclError):
                pass
        if foto_no_cartao[0] is None:
            tela.create_text(
                465, 230, text=iniciais, font=("Arial", 24, "bold"),
                fill="white", tags="cartao"
            )

        tela.create_text(
            532, 199, text=nome[:35],
            font=("Arial", 21, "bold"), fill=escuro,
            anchor="nw", tags="cartao"
        )
        tela.create_text(
            532, 239, text=f"@{pessoa['usuario']}  ·  {pessoa['cidade']}",
            font=("Arial", 11), fill=texto_claro,
            anchor="nw", width=625, tags="cartao"
        )

        tela.create_text(
            410, 313, text="ENSINA",
            font=("Arial", 10, "bold"), fill=verde,
            anchor="nw", tags="cartao"
        )
        tela.create_text(
            410, 338, text=pessoa["habilidade"],
            font=("Arial", 24, "bold"), fill=escuro,
            anchor="nw", width=740, tags="cartao"
        )
        tela.create_text(
            410, 385,
            text=f"Categoria: {pessoa['categoria']}",
            font=("Arial", 11), fill=texto_claro,
            anchor="nw", tags="cartao"
        )
        tela.create_text(
            410, 414, text=pessoa["descricao"][:190],
            font=("Arial", 12), fill=texto_claro,
            anchor="nw", width=730, tags="cartao"
        )
        tela.create_line(
            410, 482, 1157, 482, fill=borda, tags="cartao"
        )
        tela.create_text(
            410, 501,
            text="Quer aprender: " + pessoa["quer_aprender"][:85],
            font=("Arial", 11), fill=escuro,
            anchor="nw", width=730, tags="cartao"
        )
        sinal = (
            "✓ Combina com o que você quer aprender"
            if pessoa["interesse"] else "✧ Descubra uma habilidade diferente"
        )
        tela.create_text(
            410, 542, text=sinal,
            font=("Arial", 11, "bold"),
            fill=verde if pessoa["interesse"] else rosa,
            anchor="nw", tags="cartao"
        )
        preco_cartao = ("Troca grátis pelo BloomMatch ♡" if tem_match_reciproco(usuario_logado["id"], pessoa["professor_id"])
                        else f"Aula por {PRECO_AULA_SEM_MATCH} BloomCoins, sem precisar de match")
        tela.create_text(
            410, 574, text=preco_cartao, font=("Arial", 11),
            fill=escuro, anchor="nw", tags="cartao"
        )
        arredondado(1000, 190, 165, 38, verde, "botao_perfil_cartao")
        tela.create_text(
            1082, 209, text="Ver perfil", font=("Arial", 10, "bold"),
            fill="white", tags="botao_perfil_cartao"
        )
        tela.tag_bind("botao_perfil_cartao", "<ButtonRelease-1>",
                      lambda evento: (ver_perfil_do_cartao(), "break")[1])
        tela.tag_bind("botao_perfil_cartao", "<Enter>",
                      lambda evento: tela.config(cursor="hand2"))
        tela.tag_bind("botao_perfil_cartao", "<Leave>",
                      lambda evento: tela.config(cursor=""))

        tela.create_text(
            1217, 142,
            text=f"{atual[0]+1} de {len(sugestoes)}",
            font=("Arial", 10), fill=texto_claro,
            anchor="ne", tags="quantidade"
        )
        tela.tag_bind("cartao", "<ButtonPress-1>", inicio_arrastar)
        tela.tag_bind("cartao", "<B1-Motion>", arrastar_cartao)

    def proximo():
        atual[0] += 1
        exibir_cartao()

    def reacao(acao):
        if atual[0] >= len(sugestoes):
            messagebox.showinfo("Bloomie", "Não há cartão selecionado. Use 'Rever perfis'.", parent=match)
            return
        pessoa = sugestoes[atual[0]]
        try:
            combinou, gerou_pedido, nova_curtida = registrar_curtida_bloommatch(
                usuario_logado["id"], pessoa["habilidade_id"], acao
            )
        except (sqlite3.Error, ValueError) as erro:
            messagebox.showerror("Bloomie", f"Não foi possível salvar a curtida: {erro}", parent=match)
            return
        if acao == "curti":
            if combinou:
                if gerou_pedido:
                    mensagem = "Vocês deram match! ♡ Um convite gratuito foi enviado para a outra conta."
                elif nova_curtida:
                    mensagem = ("Vocês deram match! ♡ Já existe uma solicitação ativa entre vocês, "
                                "ou esse convite já foi registrado.")
                else:
                    mensagem = "Você já tinha curtido essa habilidade. A curtida continua salva."
            else:
                mensagem = "Curtida registrada! Quando essa pessoa curtir sua habilidade, vocês terão um match."
            messagebox.showinfo("BloomMatch ♡", mensagem, parent=match)
        #continua para o próximo cartão; o perfil pode ser revisto pelo menu lateral
        proximo()

    def ver_perfil_do_cartao():
        #mostra o perfil completo sem registrar curtida ou passar o cartão
        if atual[0] >= len(sugestoes):
            messagebox.showinfo("Bloomie", "Não há um cartão selecionado.", parent=match)
            return
        mostrar_perfil_alheio(sugestoes[atual[0]]["professor_id"], match)

    def pedir_aula_do_cartao():
        if atual[0] >= len(sugestoes):
            return
        enviar_solicitacao_de_aula(sugestoes[atual[0]]["habilidade_id"], match)

    def oferecer_aula_no_cartao():
        if atual[0] >= len(sugestoes):
            return
        oferecer_aula_para_pessoa(sugestoes[atual[0]]["professor_id"], match)

    def rever_perfis():
        perfis_vistos = carregar_sugestoes(incluir_vistos=True)
        if not perfis_vistos:
            messagebox.showinfo(
                "Bloomie", "Você ainda não curtiu nem passou nenhum perfil.",
                parent=match
            )
            return
        sugestoes[:] = perfis_vistos
        atual[0] = 0
        vendo_perfis_antigos[0] = True
        exibir_cartao()

    def abrir_quem_me_curtiu(pessoa_pre_selecionada=None, ao_concluir=None):
        janela_curtidas = tk.Toplevel(match)
        janela_curtidas.title("Bloomie - Quem me curtiu")
        janela_curtidas.geometry("1030x620")
        janela_curtidas.resizable(False, False)
        janela_curtidas.configure(bg="#FFF7F3")
        aplicar_fundo_funcionalidades(janela_curtidas, 1030, 620)

        tk.Label(
            janela_curtidas,
            text="Quem me curtiu ♡",
            font=("Arial", 25, "bold"),
            fg=escuro, bg="#FFF7F3"
        ).place(x=40, y=30)

        tk.Label(
            janela_curtidas,
            text=(f"conta: @{usuario_logado['usuario']} · as habilidades abaixo são SUAS, "
                  "curtidas por outras pessoas."),
            font=("Arial", 12),
            fg=texto_claro, bg="#FFF7F3"
        ).place(x=42, y=78)

        colunas = ("nome", "usuario", "habilidades", "situacao")
        tabela_curtidas = ttk.Treeview(
            janela_curtidas,
            columns=colunas,
            show="headings",
            selectmode="browse",
            height=12
        )

        for coluna, titulo, largura in (
            ("nome", "Nome", 220),
            ("usuario", "Usuário", 175),
            ("habilidades", "Suas habilidades curtidas", 340),
            ("situacao", "Situação", 215)
        ):
            tabela_curtidas.heading(coluna, text=titulo)
            tabela_curtidas.column(coluna, width=largura, anchor="center")

        tabela_curtidas.place(x=38, y=140, width=950, height=350)

        rolagem = ttk.Scrollbar(
            janela_curtidas, orient="vertical", command=tabela_curtidas.yview
        )
        rolagem.place(x=988, y=140, height=350)
        tabela_curtidas.configure(yscrollcommand=rolagem.set)

        texto_resultado = tk.Label(
            janela_curtidas, text="",
            font=("Arial", 11), fg=texto_claro, bg="#FFF7F3"
        )
        texto_resultado.place(x=40, y=510)

        def atualizar_curtidas():
            for item in tabela_curtidas.get_children():
                tabela_curtidas.delete(item)

            pessoas = consultar_curtidas_recebidas(usuario_logado["id"])
            for pessoa_id, nome, usuario, habilidades, reciproco in pessoas:
                situacao = "BloomMatch ♡" if reciproco else "Curtiu suas habilidades"
                tabela_curtidas.insert("", "end", iid=str(pessoa_id), values=(
                    nome, "@" + usuario, habilidades or "", situacao
                ))

            if pessoas:
                texto_resultado.configure(
                    text=f"{len(pessoas)} pessoa(s) curtiram suas habilidades."
                )
            else:
                texto_resultado.configure(
                    text="Ainda ninguém curtiu suas habilidades."
                )

        def curtir_de_volta():
            selecao = tabela_curtidas.selection()
            if not selecao:
                messagebox.showwarning(
                    "Bloomie", "Selecione uma pessoa para curtir de volta.",
                    parent=janela_curtidas
                )
                return

            pessoa_id = int(selecao[0])
            cursor.execute("SELECT nome FROM usuarios WHERE id = ?", (pessoa_id,))
            dados_pessoa = cursor.fetchone()
            if not dados_pessoa:
                messagebox.showwarning(
                    "Bloomie", "Essa conta não está mais disponível.",
                    parent=janela_curtidas
                )
                atualizar_curtidas()
                return

            nome_pessoa = dados_pessoa[0]
            cursor.execute("""
                SELECT 1 FROM bloommatch_reacoes r
                JOIN habilidades h ON h.id = r.habilidade_id
                WHERE r.usuario_id = ? AND h.usuario_id = ? AND r.acao = 'curti'
                LIMIT 1
            """, (usuario_logado["id"], pessoa_id))
            if cursor.fetchone():
                messagebox.showinfo(
                    "BloomMatch ♡",
                    f"Você e {nome_pessoa} já curtiram habilidades um do outro!",
                    parent=janela_curtidas
                )
                return

            cursor.execute("""
                SELECT id, habilidade, categoria FROM habilidades
                WHERE usuario_id = ? ORDER BY habilidade COLLATE NOCASE
            """, (pessoa_id,))
            habilidades_pessoa = cursor.fetchall()
            if not habilidades_pessoa:
                messagebox.showinfo(
                    "Bloomie", "Essa pessoa ainda não tem habilidades disponíveis.",
                    parent=janela_curtidas
                )
                return

            janela_escolha = tk.Toplevel(janela_curtidas)
            janela_escolha.title("Bloomie - Curtir de volta")
            janela_escolha.geometry("510x410")
            janela_escolha.resizable(False, False)
            janela_escolha.configure(bg="#FFF7F3")
            aplicar_fundo_funcionalidades(janela_escolha, 510, 410)
            janela_escolha.transient(janela_curtidas)
            janela_escolha.grab_set()

            tk.Label(
                janela_escolha, text=f"Curtir {nome_pessoa} de volta ♡",
                font=("Arial", 19, "bold"), fg=escuro, bg="#FFF7F3",
                wraplength=455
            ).place(x=30, y=25)
            tk.Label(
                janela_escolha,
                text="Escolha qual habilidade dessa pessoa você quer curtir:",
                font=("Arial", 11), fg=texto_claro, bg="#FFF7F3"
            ).place(x=30, y=85)

            lista_habilidades = tk.Listbox(
                janela_escolha, font=("Arial", 11),
                bg="#FFF7F3", fg=escuro, selectbackground="#D5A7B1",
                relief="flat", highlightthickness=1, highlightbackground="#D5B8B1",
                exportselection=False
            )
            lista_habilidades.place(x=30, y=125, width=450, height=172)
            for _, habilidade, categoria in habilidades_pessoa:
                lista_habilidades.insert("end", f"{habilidade}  ·  {categoria}")
            if len(habilidades_pessoa) == 1:
                lista_habilidades.selection_set(0)

            def confirmar_curtida():
                indice = lista_habilidades.curselection()
                if not indice:
                    messagebox.showwarning(
                        "Bloomie", "Selecione uma habilidade primeiro.",
                        parent=janela_escolha
                    )
                    return

                habilidade_id = habilidades_pessoa[indice[0]][0]
                try:
                    combinou, gerou_pedido, _ = registrar_curtida_bloommatch(
                        usuario_logado["id"], habilidade_id
                    )
                except (sqlite3.Error, ValueError) as erro:
                    messagebox.showerror("Bloomie", f"Não foi possível curtir: {erro}", parent=janela_escolha)
                    return

                janela_escolha.destroy()
                atualizar_curtidas()
                if ao_concluir:
                    ao_concluir()
                sugestoes[:] = carregar_sugestoes()
                atual[0] = 0
                exibir_cartao()
                messagebox.showinfo(
                    "BloomMatch! ♡",
                    f"Você e {nome_pessoa} curtiram habilidades um do outro! 🌸\n"
                    + ("A solicitação de troca gratuita foi enviada automaticamente."
                       if gerou_pedido else "A solicitação de vocês já está registrada."),
                    parent=janela_curtidas
                )

            lista_habilidades.bind("<Double-Button-1>", lambda evento: confirmar_curtida())
            botao_suave(
                janela_escolha, "♡ Curtir habilidade", confirmar_curtida,
                largura=190, cor=verde
            ).place(x=47, y=333)
            botao_suave(
                janela_escolha, "Cancelar", janela_escolha.destroy,
                largura=190
            ).place(x=270, y=333)

        def pedir_aula_de_quem_curtiu():
            selecao = tabela_curtidas.selection()
            if not selecao:
                messagebox.showwarning("Bloomie", "Selecione uma pessoa primeiro.", parent=janela_curtidas)
                return
            escolher_aula_com_pessoa(int(selecao[0]), janela_curtidas, atualizar_curtidas)

        def oferecer_aula_para_quem_curtiu():
            selecao = tabela_curtidas.selection()
            if not selecao:
                messagebox.showwarning("Bloomie", "Selecione uma pessoa primeiro.", parent=janela_curtidas)
                return
            oferecer_aula_para_pessoa(int(selecao[0]), janela_curtidas, atualizar_curtidas)

        botao_suave(janela_curtidas, "Atualizar", atualizar_curtidas, largura=155, cor=verde).place(x=12, y=553)
        botao_suave(janela_curtidas, "♡ Curtir de volta", curtir_de_volta, largura=155, cor=verde).place(x=182, y=553)
        botao_suave(janela_curtidas, "Pedir aula", pedir_aula_de_quem_curtiu, largura=155, cor=verde).place(x=352, y=553)
        botao_suave(janela_curtidas, "Oferecer aula", oferecer_aula_para_quem_curtiu, largura=155, cor=verde).place(x=522, y=553)
        botao_suave(janela_curtidas, "Minhas solicitações", abrir_solicitacoes, largura=155, cor=verde).place(x=692, y=553)
        botao_suave(janela_curtidas, "Voltar", janela_curtidas.destroy, largura=155).place(x=862, y=553)
        atualizar_curtidas()
        if pessoa_pre_selecionada is not None:
            item = str(pessoa_pre_selecionada)
            if tabela_curtidas.exists(item):
                tabela_curtidas.selection_set(item)
                tabela_curtidas.focus(item)
                tabela_curtidas.see(item)

    def combinar_aula_bloommatch():
        garantir_colunas_solicitacoes()
        usuario_id = usuario_logado["id"]
        janela_agendas = tk.Toplevel(match)
        janela_agendas.title("Bloomie - Combinar aula")
        janela_agendas.geometry("800x550")
        janela_agendas.resizable(False, False)
        janela_agendas.configure(bg=creme)
        aplicar_fundo_funcionalidades(janela_agendas, 800, 550)
        janela_agendas.transient(match)
        janela_agendas.lift(match)
        janela_agendas.focus_set()

        tk.Label(
            janela_agendas, text="Combinar aula 🌸",
            font=("Arial", 22, "bold"), bg=creme, fg=escuro
        ).place(x=32, y=24)
        tk.Label(
            janela_agendas,
            text="Match: troca grátis. Sem match: aula por 5 BloomCoins.",
            font=("Arial", 11), bg=creme, fg=texto_claro
        ).place(x=33, y=73)
        tk.Label(
            janela_agendas,
            text="Depois de aceitar o pedido, definam a data e entrem na sala online.",
            font=("Arial", 10), bg=creme, fg=texto_claro
        ).place(x=33, y=95)

        colunas_agenda = ("pessoa", "habilidade", "status", "situacao")
        tabela_agenda = ttk.Treeview(
            janela_agendas, columns=colunas_agenda,
            show="headings", selectmode="browse", height=9
        )
        for coluna, titulo, largura in (
            ("pessoa", "Pessoa", 176),
            ("habilidade", "Habilidade", 206),
            ("status", "Situação", 116),
            ("situacao", "Próxima etapa", 210)
        ):
            tabela_agenda.heading(coluna, text=titulo)
            tabela_agenda.column(coluna, width=largura, anchor="center")
        tabela_agenda.place(x=33, y=137, width=708, height=280)

        barra_agenda = ttk.Scrollbar(
            janela_agendas, orient="vertical", command=tabela_agenda.yview
        )
        barra_agenda.place(x=741, y=137, height=280)
        tabela_agenda.configure(yscrollcommand=barra_agenda.set)

        aviso_agenda = tk.Label(
            janela_agendas, text="", font=("Arial", 10),
            bg=creme, fg=texto_claro, anchor="w", justify="left"
        )
        aviso_agenda.place(x=34, y=427, width=725)
        linhas_agenda = {}

        def _atualizar_agendas_dados():
            selecao_anterior = tabela_agenda.selection()
            for item in tabela_agenda.get_children():
                tabela_agenda.delete(item)
            linhas_agenda.clear()

            sincronizar_matches_em_pedidos(usuario_id)
            matches = listar_matches_para_agendamento(usuario_id)

            cursor.execute("""
                SELECT s.id, COALESCE(u.nome, 'Conta indisponível'),
                       COALESCE(h.habilidade, 'Habilidade removida'),
                       s.status, COALESCE(s.situacao_agendamento, 'sem_proposta'),
                       CASE WHEN s.aluno_id = ? THEN 'Professor' ELSE 'Aluno' END,
                       s.aluno_id, s.professor_id,
                       COALESCE(s.solicitado_por, s.aluno_id), s.proposta_por
                FROM solicitacoes s
                LEFT JOIN usuarios u ON u.id = CASE
                    WHEN s.aluno_id = ? THEN s.professor_id
                    ELSE s.aluno_id END
                LEFT JOIN habilidades h ON h.id = s.habilidade_id
                WHERE s.aluno_id = ? OR s.professor_id = ?
                ORDER BY CASE s.status
                    WHEN 'aceita' THEN 0
                    WHEN 'pendente' THEN 1
                    WHEN 'concluida' THEN 2
                    ELSE 3 END, s.id DESC
            """, (usuario_id, usuario_id, usuario_id, usuario_id))
            registros = cursor.fetchall()
            cursor.execute("""
                SELECT CASE WHEN aluno_id = ? THEN professor_id ELSE aluno_id END
                FROM solicitacoes WHERE aluno_id = ? OR professor_id = ?
            """, (usuario_id, usuario_id, usuario_id))
            pessoas_com_pedido = {linha[0] for linha in cursor.fetchall()}
            pessoas_com_match = {linha[0] for linha in matches}
            situacoes = {
                "sem_proposta": "Aguardando proposta",
                "alteracao_solicitada": "Alteração solicitada",
                "confirmado": "Aula agendada"
            }
            situacao_pedido = {
                "aceita": "Aceita",
                "pendente": "Pendente",
                "concluida": "Concluída",
                "recusada": "Recusada",
                "cancelada": "Cancelada"
            }
            for numero, pessoa, habilidade, status, situacao, papel, aluno_id, professor_id, remetente_id, proposta_por in registros:
                chave = f"pedido-{numero}"
                linhas_agenda[chave] = ("pedido", numero, status, papel, remetente_id != usuario_id)
                outra_pessoa = professor_id if aluno_id == usuario_id else aluno_id
                titulo_status = situacao_pedido.get(status, status.capitalize())
                if outra_pessoa in pessoas_com_match:
                    titulo_status += " ♡"
                tabela_agenda.insert(
                    "", "end", iid=chave,
                    values=(
                        f"{pessoa} ({papel})", habilidade,
                        titulo_status,
                        ("Aceitar horário" if proposta_por != usuario_id else "Aguardando aceite")
                        if status == "aceita" and situacao == "proposta" else
                        situacoes.get(situacao, "Aguardando proposta")
                        if status == "aceita" else
                        ("Aceitar ou recusar oferta" if status == "pendente" and remetente_id != usuario_id
                         else "Aguardando resposta" if status == "pendente" else "—")
                    )
                )

            for pessoa_id, nome, usuario, habilidades, habilidade_id in matches:
                if pessoa_id in pessoas_com_pedido:
                    continue
                chave = f"match-{pessoa_id}"
                linhas_agenda[chave] = ("match", pessoa_id, "reciproco", "", habilidade_id)
                tabela_agenda.insert(
                    "", "end", iid=chave,
                    values=(f"{nome} (@{usuario})", habilidades or "Habilidade disponível",
                            "BloomMatch ♡", "Preparando solicitação")
                )

            curtidas_recebidas = consultar_curtidas_recebidas(usuario_id)
            curtidas_sem_resposta = 0
            for pessoa_id, nome, usuario, habilidades, reciproco in curtidas_recebidas:
                if pessoa_id in pessoas_com_match or pessoa_id in pessoas_com_pedido:
                    continue
                if reciproco:
                    chave = f"match-{pessoa_id}"
                    if chave in linhas_agenda:
                        continue
                    linhas_agenda[chave] = ("match", pessoa_id, "reciproco", "", None)
                    situacao = "BloomMatch ♡"
                    proxima_etapa = "Preparando solicitação"
                else:
                    curtidas_sem_resposta += 1
                    chave = f"curtida-{pessoa_id}"
                    linhas_agenda[chave] = ("curtida", pessoa_id, "aguardando", "")
                    situacao = "Curtiu você ♡"
                    proxima_etapa = "Pedir ou oferecer aula"
                tabela_agenda.insert(
                    "", "end", iid=chave,
                    values=(f"{nome} (@{usuario})", habilidades or "Suas habilidades",
                            situacao, proxima_etapa)
                )

            if selecao_anterior and tabela_agenda.exists(selecao_anterior[0]):
                tabela_agenda.selection_set(selecao_anterior[0])
            else:
                itens = tabela_agenda.get_children()
                aceitos = [item for item in itens if linhas_agenda[item][2] == "aceita"]
                recebidos_pendentes = [item for item in itens if
                                       linhas_agenda[item][2] == "pendente" and
                                       linhas_agenda[item][4]]
                opcoes = aceitos or recebidos_pendentes or itens
                if opcoes:
                    tabela_agenda.selection_set(opcoes[0])
                    tabela_agenda.focus(opcoes[0])
                    tabela_agenda.see(opcoes[0])

            aceitas = sum(1 for registro in registros if registro[3] == "aceita")
            pendentes = sum(1 for registro in registros if registro[3] == "pendente")
            if linhas_agenda:
                aviso_agenda.config(
                    text=f"{len(matches)} BloomMatch(es)  ·  {curtidas_sem_resposta} curtida(s) aguardando você  ·  "
                         f"{aceitas} aceito(s)  ·  {pendentes} pendente(s)"
                )
            else:
                aviso_agenda.config(
                    text="Nenhum pedido nem curtida nesta conta. Se outra tela mostra curtidas, "
                         "feche as janelas antigas e abra o BloomMatch novamente. "
                         f"Banco usado: {os.path.join(PASTA_PROJETO, 'bloomie.db')}"
                )

        def atualizar_agendas():
            try:
                _atualizar_agendas_dados()
                #atualiza também as ações do pedido que ficou selecionado
                atualizar_botoes_agenda()
                janela_agendas.after_idle(atualizar_botoes_agenda)
            except sqlite3.Error as erro:
                messagebox.showerror(
                    "Bloomie - Combinar aula",
                    f"Não foi possível carregar as aulas.\nErro: {erro}\n"
                    f"Banco: {os.path.join(PASTA_PROJETO, 'bloomie.db')}",
                    parent=janela_agendas
                )

        def linha_selecionada():
            selecao = tabela_agenda.selection()
            if not selecao:
                messagebox.showwarning(
                    "Bloomie", "Selecione uma pessoa ou solicitação na lista.",
                    parent=janela_agendas
                )
                return None
            return linhas_agenda.get(selecao[0])

        def oferecer_aula_na_agenda():
            linha = linha_selecionada()
            if linha is None:
                return
            if linha[0] in ("curtida", "match"):
                oferecer_aula_para_pessoa(linha[1], janela_agendas, atualizar_agendas)

        def abrir_aula_selecionada():
            linha = linha_selecionada()
            if linha is None:
                return
            if linha[0] == "curtida":
                escolher_aula_com_pessoa(linha[1], janela_agendas, atualizar_agendas)
                return
            if linha[0] == "match":
                sincronizar_matches_em_pedidos(usuario_id)
                atualizar_agendas()
                messagebox.showinfo(
                    "Bloomie", "O BloomMatch é recíproco. Confira a solicitação na lista atualizada.",
                    parent=janela_agendas
                )
                return
            combinar_pedido_ou_aceitar(linha[1], janela_agendas, atualizar_agendas)

        def abrir_item_selecionado():
            linha = linha_selecionada()
            if linha is None:
                return
            abrir_aula_selecionada()

        def responder_pedido_no_match(aceitar):
            linha = linha_selecionada()
            if linha is None:
                return
            if linha[0] != "pedido":
                messagebox.showinfo("Bloomie", "Selecione uma solicitação de aula.", parent=janela_agendas)
                return
            if aceitar and linha[2] == "aceita":
                abrir_aula_selecionada()
                return
            if aceitar and (linha[2] != "pendente" or not linha[4]):
                messagebox.showinfo("Bloomie", "Só é possível aceitar pedidos pendentes recebidos.", parent=janela_agendas)
                return
            if not aceitar and linha[2] not in ("pendente", "aceita"):
                messagebox.showinfo("Bloomie", "Esta solicitação já foi finalizada.", parent=janela_agendas)
                return
            if not aceitar and not messagebox.askyesno(
                "Bloomie", "Deseja desistir da aula? O pedido ficará salvo no histórico.", parent=janela_agendas
            ):
                return
            try:
                mensagem = (responder_solicitacao(linha[1], usuario_id, True) if aceitar
                            else desistir_solicitacao(linha[1], usuario_id))
            except sqlite3.Error as erro:
                messagebox.showerror("Bloomie", f"Erro ao responder pedido: {erro}", parent=janela_agendas)
                return
            messagebox.showinfo("Bloomie 🌸", mensagem, parent=janela_agendas)
            atualizar_agendas()

        tabela_agenda.bind("<Double-1>", lambda evento: abrir_item_selecionado())
        def abrir_sala_selecionada():
            linha = linha_selecionada()
            if linha is None or linha[0] != "pedido":
                return
            abrir_sala_online(linha[1], janela_agendas)

        def aceitar_horario_selecionado():
            linha = linha_selecionada()
            if linha and linha[0] == "pedido":
                responder_proposta_horario(linha[1], janela_agendas, atualizar_agendas, True)

        def pedir_alteracao_selecionada():
            linha = linha_selecionada()
            if linha and linha[0] == "pedido":
                responder_proposta_horario(linha[1], janela_agendas, atualizar_agendas, False)

        def concluir_aula_selecionada():
            linha = linha_selecionada()
            if linha and linha[0] == "pedido":
                confirmar_conclusao_aula(linha[1], janela_agendas, atualizar_agendas)

        def curtir_de_volta_na_agenda():
            linha = linha_selecionada()
            if linha is None:
                return
            if linha[0] != "curtida":
                messagebox.showinfo(
                    "Bloomie", "Esse perfil não tem uma curtida pendente. "
                    "Selecione alguém com a situação 'Curtiu você ♡'.", parent=janela_agendas
                )
                return
            abrir_quem_me_curtiu(linha[1], atualizar_agendas)

        #os botões arredondados mudam com a seleção, sem misturar ações entre perfis
        botao_principal_agenda, configurar_principal_agenda = botao_suave_dinamico(
            janela_agendas, largura=194, altura=40, cor=verde
        )
        botao_secundario_agenda, configurar_secundario_agenda = botao_suave_dinamico(
            janela_agendas, largura=194, altura=40, cor=rosa
        )
        orientacao_agenda = tk.Label(
            janela_agendas, text="", bg=creme, fg=escuro,
            font=("Arial", 10), anchor="w"
        )
        orientacao_agenda.place(x=34, y=451, width=720, height=20)

        def atualizar_botoes_agenda(evento=None):
            if not janela_agendas.winfo_exists():
                return
            selecao = tabela_agenda.selection()
            chave = selecao[0] if selecao else None
            linha = linhas_agenda.get(chave)
            principal = None
            secundario = None
            orientacao = "selecione um pedido ou curtida para ver as ações disponíveis"

            if linha:
                if linha[0] == "curtida":
                    orientacao = "sem match: peça para aprender ou ofereça uma habilidade sua"
                    principal = ("Pedir aula (5 moedas)", abrir_aula_selecionada)
                    secundario = ("Dar aula (oferecer)", oferecer_aula_na_agenda)
                elif linha[0] == "match":
                    orientacao = "match recíproco: troca gratuita. você também pode ensinar."
                    principal = ("Ver solicitação", abrir_aula_selecionada)
                    secundario = ("Dar aula (oferecer)", oferecer_aula_na_agenda)
                else:
                    numero, estado, papel = linha[1:4]
                    if estado == "pendente":
                        if linha[4]:
                            orientacao = "você recebeu esse pedido e pode aceitar ou recusar"
                            principal = ("Aceitar pedido", lambda: responder_pedido_no_match(True))
                            secundario = ("Recusar pedido", lambda: responder_pedido_no_match(False))
                        else:
                            orientacao = "seu pedido aguarda a resposta do professor"
                            secundario = ("Cancelar pedido", lambda: responder_pedido_no_match(False))
                    elif estado == "aceita":
                        try:
                            agendamento = banco.consultar_agendamento(numero, usuario_id)
                        except sqlite3.Error as erro:
                            messagebox.showerror("Bloomie", str(erro), parent=janela_agendas)
                            agendamento = None
                        situacao = (agendamento or {}).get("situacao_agendamento") or "sem_proposta"
                        if situacao == "confirmado":
                            professor = agendamento and agendamento.get("professor_id") == usuario_id
                            ja_confirmou = (agendamento.get("confirmado_professor") if professor
                                           else (agendamento or {}).get("confirmado_aluno"))
                            orientacao = ("sua confirmação foi registrada; falta a outra pessoa"
                                          if ja_confirmou else "aula agendada: confirme apenas depois que acontecer")
                            if agendamento and agendamento.get("modalidade_aula") == "online":
                                principal = ("Sala online", abrir_sala_selecionada)
                            else:
                                principal = ("Ver agendamento", abrir_aula_selecionada)
                            if not ja_confirmou:
                                secundario = ("Marcar aula dada" if professor else "Confirmar recebida",
                                              concluir_aula_selecionada)
                        elif situacao == "proposta" and agendamento and agendamento.get("proposta_por") != usuario_id:
                            orientacao = "a outra pessoa enviou a proposta: aceite o horário ou peça mudança"
                            principal = ("Aceitar horário", aceitar_horario_selecionado)
                            secundario = ("Pedir alteração", pedir_alteracao_selecionada)
                        elif situacao == "alteracao_solicitada" and agendamento:
                            if agendamento.get("proposta_por") == usuario_id:
                                pedido = agendamento.get("pedido_alteracao") or "a outra pessoa pediu um ajuste no horário"
                                orientacao = "a outra pessoa pediu alteração: " + pedido
                                principal = ("Responder alteração", abrir_aula_selecionada)
                            else:
                                orientacao = "seu pedido de alteração foi enviado; aguardando novo horário"
                                principal = ("Ver pedido", abrir_aula_selecionada)
                        else:
                            orientacao = ("sua proposta foi enviada; aguarde a outra pessoa"
                                          if situacao == "proposta" else
                                          "pedido aceito: defina a data e a modalidade da aula")
                            principal = ("Ver proposta" if situacao == "proposta" else "Combinar aula",
                                         abrir_aula_selecionada)
                    elif estado == "concluida":
                        orientacao = "aula concluída: veja os detalhes ou combine uma nova aula"
                        principal = ("Ver detalhes", lambda pid=numero: ver_detalhes_aula_concluida(pid, janela_agendas))
                        secundario = ("Nova aula", lambda pid=numero: pedir_nova_aula_de_pedido(pid, janela_agendas, atualizar_agendas))
                    else:
                        orientacao = "pedido cancelado ou recusado; faça um novo pedido para outra aula"

            orientacao_agenda.config(text=orientacao)
            botao_principal_agenda.place_forget()
            botao_secundario_agenda.place_forget()
            if principal:
                configurar_principal_agenda(principal[0], principal[1])
                botao_principal_agenda.place(
                    x=199 if secundario else 306, y=485, width=194, height=40
                )
            if secundario:
                configurar_secundario_agenda(secundario[0], secundario[1])
                botao_secundario_agenda.place(x=410, y=485, width=194, height=40)

        tabela_agenda.bind("<<TreeviewSelect>>", atualizar_botoes_agenda)
        tabela_agenda.bind(
            "<ButtonRelease-1>",
            lambda evento: janela_agendas.after_idle(atualizar_botoes_agenda)
        )
        botao_suave(janela_agendas, "Atualizar", atualizar_agendas,
                    largura=140, cor=verde).place(x=33, y=485)
        botao_suave(janela_agendas, "Voltar", janela_agendas.destroy,
                    largura=140).place(x=625, y=485)
        atualizar_agendas()

    def inicio_arrastar(evento):
        inicio_arrasto[0] = evento.x
        ultimo_x[0] = evento.x

    def arrastar_cartao(evento):
        if inicio_arrasto[0] is None:
            return
        tela.move("cartao", evento.x - ultimo_x[0], 0)
        ultimo_x[0] = evento.x

    def fim_arrastar(evento):
        if inicio_arrasto[0] is None:
            return
        distancia = evento.x - inicio_arrasto[0]
        inicio_arrasto[0] = None
        ultimo_x[0] = None
        if distancia >= 100:
            reacao("curti")
        elif distancia <= -100:
            reacao("passei")
        else:
            tela.move("cartao", -distancia, 0)

    #também dá pra usar as setas do teclado
    match.bind("<Left>", lambda evento: reacao("passei"))
    match.bind("<Right>", lambda evento: reacao("curti"))
    tela.bind("<ButtonRelease-1>", fim_arrastar)

    #os perfis completos ficam no bloommatch, inclusive os cartões já passados
    #os perfis são abertos pelo cartão atual ou em rever perfis

    #menu lateral fica separado dos botões de aprender e ensinar
    botao(1000, 100, 214, "♡ Quem me curtiu", abrir_quem_me_curtiu, "quem_me_curtiu", verde)
    botao(35, 450, 200, "Rever perfis", rever_perfis, "rever_match", verde)
    botao(35, 506, 200, "Minhas habilidades", abrir_minhas_habilidades,
          "minhas_habilidades_match", verde)
    botao(35, 562, 200, "Minhas solicitações", abrir_solicitacoes, "solicitacoes_match")
    botao(35, 618, 200, "← Voltar", match.destroy, "voltar_match")

    #aprender e ensinar são escolhas diferentes; nenhuma delas precisa de curtida
    botao(328, 670, 185, "✕ Passar", lambda: reacao("passei"), "pular_match", "#B9A19D")
    botao(526, 670, 185, "♡ Curtir", lambda: reacao("curti"), "curtir_match", verde)
    botao(724, 670, 205, "Pedir aula", pedir_aula_do_cartao, "pedir_match", verde)
    botao(942, 670, 225, "Dar aula (oferecer)", oferecer_aula_no_cartao, "oferecer_match", verde)
    tela.create_text(
        742, 644, text="Pedir para aprender  ·  Dar aula usando uma habilidade sua",
        font=("Arial", 10), fill=texto_claro, anchor="nw"
    )
    tela.create_text(
        358, 749,
        text="← Passar    |    Curtir →    |    Arraste o cartão para os lados",
        font=("Arial", 10), fill=texto_claro, anchor="nw"
    )
    exibir_cartao()
    tela.tag_raise("pular_match")
    tela.tag_raise("curtir_match")


def sair_da_conta():
    global usuario_logado

    cursor.execute("DELETE FROM sessao where id=1")
    conexao.commit()

    usuario_logado = None

    for aberta in janela.winfo_children():
        if isinstance(aberta, tk.Toplevel):
            aberta.destroy()

    #sem sessão ativa, não deixa as janelas antigas abertas
    janela.withdraw()
    abrir_tela_login()


def apagar_conta(usuario_id):
    try:
        cursor.execute("BEGIN IMMEDIATE") #inicia a exclusão no banco

        cursor.execute("""
            DELETE FROM sala_online_mensagens
            WHERE remetente_id = ? OR pedido_id IN (
                SELECT id FROM solicitacoes WHERE aluno_id = ? OR professor_id = ?
            )
        """, (usuario_id, usuario_id, usuario_id))

        cursor.execute("""
            DELETE FROM solicitacoes
            WHERE aluno_id = ? OR professor_id = ?
               OR habilidade_id IN (
                   SELECT id FROM habilidades WHERE usuario_id = ?
               )
        """, (usuario_id, usuario_id, usuario_id))

        cursor.execute("""
            DELETE FROM interesses_habilidades
            WHERE usuario_id = ? OR habilidade_id IN (
                SELECT id FROM habilidades WHERE usuario_id = ?
            )
        """, (usuario_id, usuario_id))

        cursor.execute("""
            DELETE FROM bloommatch_reacoes
            WHERE usuario_id = ? OR habilidade_id IN (
                SELECT id FROM habilidades WHERE usuario_id = ?
            )
        """, (usuario_id, usuario_id))

        for tabela in (
            "historico_bloomcoins",
            "missoes_concluidas",
            "bloomcoins",
            "perfis",
            "habilidades"
        ):
            cursor.execute(
                f"DELETE FROM {tabela} WHERE usuario_id = ?",
                (usuario_id,)
            )

        cursor.execute("DELETE FROM sessao WHERE usuario_id = ?", (usuario_id,))
        cursor.execute("DELETE FROM codigos_email WHERE usuario_id = ?", (usuario_id,))
        cursor.execute("""
            DELETE FROM bloommatch_convites
            WHERE usuario_menor_id = ? OR usuario_maior_id = ?
        """, (usuario_id, usuario_id))

        cursor.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        if cursor.rowcount != 1:
            raise sqlite3.IntegrityError("Conta não encontrada.")

        conexao.commit()

    except sqlite3.Error:
        conexao.rollback() #desfaz a exclusão se der erro
        raise

    for extensao in (".png", ".gif"):
        caminho_foto = os.path.join(
            PASTA_PROJETO, "fotos_bloomie", f"perfil_{usuario_id}{extensao}"
        )
        if os.path.isfile(caminho_foto):
            try:
                os.remove(caminho_foto)
            except OSError:
                pass


def abrir_configuracoes(definir_frase=False):
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    try:
        garantir_campos_recuperacao()
    except (sqlite3.Error, OSError) as erro:
        messagebox.showerror("Bloomie", f"Não foi possível preparar as configurações: {erro}")
        return

    configuracoes = tk.Toplevel(janela)
    configuracoes.title("Bloomie - Configurações")
    configuracoes.geometry("1300x800")
    configuracoes.resizable(False, False)

    tela_config = tk.Canvas(configuracoes, width=1300, height=800, bg="#F8E8F0", highlightthickness=0, borderwidth=0)
    tela_config.pack()

    caminho_fundo = os.path.join(PASTA_PROJETO, "fundo_bloomie_funcionalidades.gif")
    try:
        imagem_config = tk.PhotoImage(file=caminho_fundo)
        configuracoes.imagem_fundo = imagem_config
        tela_config.create_image(0, 0, image=imagem_config, anchor="nw")
    except (tk.TclError, OSError) as erro:
        print("Não foi possível carregar o fundo das Configurações:", erro)

    rosa = "#BC838D"
    escuro = "#713D4D"
    claro = "#FFF7F3"
    verde = "#89998B"
    bege = "#B69B89"

    def arredondado(x, y, largura, altura, cor, tag=None):
        raio = min(20, largura // 2, altura // 2)
        opcoes = {"fill": cor, "outline": "", "tags": tag}
        tela_config.create_oval(x, y, x + 2 * raio, y + 2 * raio, **opcoes)
        tela_config.create_oval(x + largura - 2 * raio, y, x + largura, y + 2 * raio, **opcoes)
        tela_config.create_oval(x, y + altura - 2 * raio, x + 2 * raio, y + altura, **opcoes)
        tela_config.create_oval(x + largura - 2 * raio, y + altura - 2 * raio, x + largura, y + altura, **opcoes)
        tela_config.create_rectangle(x + raio, y, x + largura - raio, y + altura, **opcoes)
        tela_config.create_rectangle(x, y + raio, x + largura, y + altura - raio, **opcoes)

    def escrever(x, y, mensagem, tamanho=12, negrito=False, cor=escuro, tag=None):
        tela_config.create_text(x, y, text=mensagem, anchor="nw", fill=cor,
                                font=("Arial", tamanho, "bold" if negrito else "normal"), tags=tag)

    def botao(x, y, largura, mensagem, comando, tag, cor=rosa):
        arredondado(x, y, largura, 42, cor, tag)
        tela_config.create_text(x + largura / 2, y + 21, text=mensagem,
                                font=("Arial", 11, "bold"), fill="white", tags=tag)
        tela_config.tag_bind(tag, "<Button-1>", lambda evento: comando())
        tela_config.tag_bind(tag, "<Enter>", lambda evento: tela_config.config(cursor="hand2"))
        tela_config.tag_bind(tag, "<Leave>", lambda evento: tela_config.config(cursor=""))

    def campo(y, titulo, valor=""):
        escrever(370, y, titulo, 11, True)
        arredondado(365, y + 24, 835, 41, "#D5B8B1")
        arredondado(367, y + 26, 831, 37, claro)
        entrada = tk.Entry(configuracoes, font=("Arial", 12), bg=claro, fg=escuro,
                           insertbackground=escuro, relief="flat", bd=0)
        entrada.place(x=385, y=y + 31, width=795, height=26)
        entrada.insert(0, valor)
        return entrada

    def menu(texto, y, comando, tag, ativo=False):
        if ativo:
            arredondado(14, y - 7, 217, 42, "#F0D6D7", tag)
        escrever(34, y + 5, texto, 11, ativo, tag=tag)
        tela_config.tag_bind(tag, "<Button-1>", lambda evento: comando())
        tela_config.tag_bind(tag, "<Enter>", lambda evento: tela_config.config(cursor="hand2"))
        tela_config.tag_bind(tag, "<Leave>", lambda evento: tela_config.config(cursor=""))

    escrever(30, 32, "Bloomie 🌸", 25, True, "#AD6B7A")
    tela_config.create_line(24, 660, 224, 660, fill="#D6B6B5")
    menu("⌂  Início", 119, lambda: configuracoes.lower(), "config_inicio")
    menu("⌕  Explorar", 170, abrir_explorar_habilidades, "config_explorar")
    menu("♡  BloomMatch", 221, abrir_bloommatch, "config_bloommatch")
    menu("⊕  Compartilhar", 272, compartilhar_habilidade, "config_compartilhar")
    menu("☷  Minhas habilidades", 323, abrir_minhas_habilidades, "config_habilidades")
    menu("♙  Meu perfil", 374, abrir_meu_perfil, "config_perfil")
    menu("❀  Jardim de Conquistas", 425, abrir_jardim_conquistas, "config_jardim")
    menu("◷  Histórico de trocas", 476, abrir_historico_trocas, "config_historico")
    menu("✦  Missões Bloomie", 527, abrir_missoes_bloomie, "config_missoes")
    menu("✉  Solicitações", 578, abrir_solicitacoes, "config_pedidos")
    menu("⚙  Configurações", 683, lambda: None, "config_atual", True)
    menu("↪  Voltar", 732, configuracoes.destroy, "config_voltar")

    escrever(345, 38, "Configurações ⚙", 27, True)
    escrever(345, 84, "Gerencie seus dados e configure sua frase de segurança.", 12)
    arredondado(325, 150, 910, 585, "#F8E9E6")
    escrever(370, 175, "Minha conta", 17, True)

    entrada_nome = campo(215, "Nome", usuario_logado["nome"])
    entrada_usuario = campo(290, "Nome de usuário", usuario_logado["usuario"])
    escrever(370, 383, "Recuperação de senha", 15, True)
    escrever(370, 416, "Sua frase de segurança será a única forma de recuperar sua senha.", 11)
    escrever(370, 442, "Cadastre uma frase privada e guarde-a em um lugar seguro.", 10)

    def salvar():
        nome = entrada_nome.get().strip()
        usuario = entrada_usuario.get().strip().lstrip("@")
        if not nome or not usuario:
            messagebox.showwarning("Bloomie", "Preencha nome e usuário.", parent=configuracoes)
            return
        try:
            cursor.execute("UPDATE usuarios SET nome = ?, usuario = ? WHERE id = ?", (nome, usuario, usuario_logado["id"]))
            conexao.commit()
        except sqlite3.IntegrityError:
            conexao.rollback()
            messagebox.showerror("Bloomie", "Esse nome de usuário já está em uso.", parent=configuracoes)
            return
        except sqlite3.Error as erro:
            conexao.rollback()
            messagebox.showerror("Bloomie", f"Erro ao salvar: {erro}", parent=configuracoes)
            return
        usuario_logado["nome"] = nome
        usuario_logado["usuario"] = usuario
        messagebox.showinfo("Bloomie", "Dados atualizados!", parent=configuracoes)
        configuracoes.destroy()

    def gerar_codigo():
        #pede a senha antes de substituir um código de recuperação antigo
        senha_atual = simpledialog.askstring(
            "Confirmar identidade", "Digite sua senha atual para gerar o código:",
            show="*", parent=configuracoes
        )
        if senha_atual is None:
            return
        cursor.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (usuario_logado["id"],))
        registro = cursor.fetchone()
        if not registro or not verificar_senha(senha_atual, registro[0]):
            messagebox.showerror("Bloomie", "Senha incorreta. Nenhum código foi alterado.", parent=configuracoes)
            return
        if not messagebox.askyesno(
            "Código de recuperação", "Gerar um novo código?\n\nO código anterior deixará de funcionar.",
            parent=configuracoes
        ):
            return
        codigo = criar_codigo_recuperacao(usuario_logado["id"])
        exibir_codigo_recuperacao(codigo, configuracoes)

    def excluir():
        #só o dono da conta, com a senha atual, consegue excluí-la
        senha_atual = simpledialog.askstring(
            "Confirmar identidade", "Digite a senha da sua conta para continuar:",
            show="*", parent=configuracoes
        )
        if senha_atual is None:
            return
        cursor.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (usuario_logado["id"],))
        registro = cursor.fetchone()
        if not registro or not verificar_senha(senha_atual, registro[0]):
            messagebox.showerror(
                "Bloomie", "Senha incorreta. A conta não foi excluída.",
                parent=configuracoes
            )
            return
        if not messagebox.askyesno(
            "Excluir minha conta",
            "Tem certeza que deseja excluir sua conta?\n\n"
            "Seu perfil, habilidades, solicitações e moedas serão excluídos definitivamente.",
            icon="warning", parent=configuracoes
        ):
            return
        try:
            apagar_conta(usuario_logado["id"])
        except sqlite3.Error as erro:
            messagebox.showerror("Bloomie", f"Não foi possível excluir a conta: {erro}", parent=configuracoes)
            return
        sair_da_conta()
        messagebox.showinfo("Bloomie", "Conta excluída. Faça login ou crie outra conta.")

    def esqueci_senha():
        abrir_recuperacao_senha(configuracoes)

    botao(370, 478, 250, "Salvar alterações", salvar, "config_salvar")
    botao(645, 478, 220, "Sair da conta", sair_da_conta, "config_sair", bege)
    botao(890, 478, 270, "Frase de segurança",
          lambda: abrir_frase_seguranca(configuracoes), "config_frase_seguranca", verde)
    escrever(372, 545, "Esqueceu a senha? Clique aqui para trocar", 12, True, tag="trocar_senha_codigo")
    tela_config.tag_bind("trocar_senha_codigo", "<Button-1>", lambda evento: esqueci_senha())
    tela_config.tag_bind("trocar_senha_codigo", "<Enter>", lambda evento: tela_config.config(cursor="hand2"))
    tela_config.tag_bind("trocar_senha_codigo", "<Leave>", lambda evento: tela_config.config(cursor=""))
    tela_config.create_line(368, 585, 1170, 585, fill="#E2C5C7")
    botao(370, 610, 250, "Excluir minha conta", excluir, "config_excluir", "#B87580")
    botao(645, 610, 220, "Voltar", configuracoes.destroy, "config_cancelar", verde)
    escrever(890, 623, "A exclusão exige sua senha e confirmação.", 10)

    entrada_nome.bind("<Return>", lambda evento: (entrada_usuario.focus_set(), "break")[1])
    entrada_nome.focus_set()
    if definir_frase:
        abrir_frase_seguranca(configuracoes)

def abrir_meu_perfil():
    if usuario_logado is None:
        messagebox.showwarning("Bloomie", "Entre na sua conta primeiro!")
        return

    janela_Perfil = tk.Toplevel(janela) 
    janela_Perfil.title("Bloomie - Meu Perfil")
    janela_Perfil.geometry("1300x800")
    janela_Perfil.resizable(False, False)


    tela_perfil = tk.Canvas(
        janela_Perfil,
        width=1300,
        height=800,
        bg="#F8E8F0",
        highlightthickness=0,
        borderwidth=0
    ) #canvas é onde ficam os desenhos da tela
    tela_perfil.pack()

    caminho_fundo_perfil = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "fundo_bloomie_funcionalidades.gif"
    )

    try:
        imagem_perfil = tk.PhotoImage(file=caminho_fundo_perfil)
        janela_Perfil.imagem_perfil = imagem_perfil
        tela_perfil.create_image(0, 0, image=imagem_perfil, anchor="nw")
    except (tk.TclError, OSError) as erro:
        print("Não foi possível carregar o fundo do perfil:", erro)
        #mesmo sem o gif, os campos e os botões continuam aparecendo

    rosa = "#BC838D"
    rosa_escuro = "#713D4D"
    rosa_claro = "#F0D6D7"
    cor_cartao = "#F8E9E6"
    cor_campo = "#FFF5F2"
    cor_borda = "#D5B8B1"
    cor_texto = "#594C50"

    def desenho_arredondado(x, y, largura, altura, raio, cor, tag=None):
        raio = min(raio, largura // 2, altura // 2)
        opcoes = {"fill": cor, "outline": "", "tags": tag}

        tela_perfil.create_oval(
            x, y, x + raio * 2, y + raio * 2, **opcoes
        )
        tela_perfil.create_oval(
            x + largura - raio * 2, y, x + largura, y + raio * 2, **opcoes
        )
        tela_perfil.create_oval(
            x, y + altura - raio * 2, x + raio * 2, y + altura, **opcoes
        )
        tela_perfil.create_oval(
            x + largura - raio * 2, y + altura - raio * 2,
            x + largura, y + altura, **opcoes
        )
        tela_perfil.create_rectangle(
            x + raio, y, x + largura - raio, y + altura, **opcoes
        )
        tela_perfil.create_rectangle(
            x, y + raio, x + largura, y + altura - raio, **opcoes
        ) #junta as formas pra deixar os cantos arredondados

    def criar_cartao(x, y, largura, altura):
        desenho_arredondado(x, y, largura, altura, 28, cor_borda) 
        desenho_arredondado(x + 1, y + 1, largura - 2, altura - 2, 27, cor_cartao) 

    def escrever(x, y, texto, tamanho=11, negrito=False, cor=rosa_escuro, tag=None):
        tela_perfil.create_text(
            x, y,
            text=texto,
            font=("Arial", tamanho, "bold" if negrito else "normal"),
            fill=cor,
            anchor="nw",
            tags=tag
        ) 

    def criar_campo(x, y, largura, altura=35, somente_leitura=False):
        desenho_arredondado(x, y, largura, altura, 17, cor_borda)
        desenho_arredondado(x + 2, y + 2, largura - 4, altura - 4, 16, cor_campo)

        campo = tk.Entry(
            janela_Perfil,
            font=("Arial", 11),
            bg=cor_campo,
            fg=cor_texto,
            insertbackground=rosa_escuro,
            relief="flat",
            bd=0,
            readonlybackground=cor_campo,
            highlightthickness=0
        )
        campo.place(x=x + 17, y=y + 7, width=largura - 34, height=altura - 14)

        if somente_leitura:
            campo.configure(state="readonly") #mostra a informação sem deixar editar

        return campo

    def criar_area_texto(x, y, largura, altura, limite):
        desenho_arredondado(x, y, largura, altura, 19, cor_borda)
        desenho_arredondado(x + 2, y + 2, largura - 4, altura - 4, 18, cor_campo)

        campo = tk.Text(
            janela_Perfil,
            font=("Arial", 10),
            bg=cor_campo,
            fg=cor_texto,
            insertbackground=rosa_escuro,
            relief="flat",
            bd=0,
            wrap="word",
            padx=1,
            pady=1,
            undo=True,
            highlightthickness=0 
        )
        campo.place(x=x + 15, y=y + 9, width=largura - 30, height=altura - 27)

        contador = tela_perfil.create_text(
            x + largura - 12, y + altura - 13,
            text=f"0/{limite}", font=("Arial", 9),
            fill="#9D8E90", anchor="e"
        )

        def contar_caracteres(evento=None):
            conteudo = campo.get("1.0", "end-1c") 

            if len(conteudo) > limite:
                campo.delete(f"1.0+{limite}c", "end-1c") 
                conteudo = campo.get("1.0", "end-1c")

            tela_perfil.itemconfig(contador, text=f"{len(conteudo)}/{limite}")
            campo.edit_modified(False)

        campo.bind("<<Modified>>", contar_caracteres) #atualiza o contador quando o texto muda
        campo.contar_caracteres = contar_caracteres
        return campo

    def criar_botao(x, y, largura, altura, texto, comando, cor=rosa, texto_cor="white", tag="botao"):
        desenho_arredondado(x, y, largura, altura, 19, cor, tag=tag)
        tela_perfil.create_text(
            x + largura / 2, y + altura / 2,
            text=texto,
            font=("Arial", 11, "bold"),
            fill=texto_cor,
            tags=tag
        ) 
        tela_perfil.tag_bind(tag, "<Button-1>", lambda evento: comando())
        tela_perfil.tag_bind(tag, "<Enter>", lambda evento: tela_perfil.config(cursor="hand2"))
        tela_perfil.tag_bind(tag, "<Leave>", lambda evento: tela_perfil.config(cursor=""))


    escrever(30, 32, "Bloomie 🌸", 25, True, "#AD6B7A")
    tela_perfil.create_line(24, 660, 224, 660, fill="#D6B6B5", width=1) 

    def botao_menu(texto, y, comando, tag, ativo=False):
        if ativo:
            desenho_arredondado(14, y - 7, 217, 42, 15, rosa_claro, tag=tag)
        escrever(
            34, y + 5, texto, 11, ativo, rosa_escuro, tag=tag
        )
        tela_perfil.tag_bind(tag, "<Button-1>", lambda evento: comando())
        tela_perfil.tag_bind(tag, "<Enter>", lambda evento: tela_perfil.config(cursor="hand2"))
        tela_perfil.tag_bind(tag, "<Leave>", lambda evento: tela_perfil.config(cursor=""))

    botao_menu("⌂  Início", 119, janela_Perfil.destroy, "menu_inicio")
    botao_menu("⌕  Explorar", 170, abrir_explorar_habilidades, "menu_explorar")
    botao_menu("♡  BloomMatch", 221, abrir_bloommatch, "menu_bloommatch")
    botao_menu("⊕  Compartilhar", 272, compartilhar_habilidade, "menu_compartilhar")
    botao_menu("☷  Minhas habilidades", 323, abrir_minhas_habilidades, "menu_habilidades")
    botao_menu("♙  Meu perfil", 374, lambda: None, "menu_perfil", ativo=True)
    botao_menu("❀  Jardim de Conquistas", 425, abrir_jardim_conquistas, "menu_jardim")
    botao_menu("◷  Histórico de trocas", 476, abrir_historico_trocas, "menu_historico")
    botao_menu("✦  Missões Bloomie", 527, abrir_missoes_bloomie, "menu_missoes")
    botao_menu("✉  Solicitações", 578, abrir_solicitacoes, "menu_pedidos")
    botao_menu("⚙  Configurações", 683, abrir_configuracoes, "menu_configuracoes")
    botao_menu("↪  Voltar", 732, janela_Perfil.destroy, "menu_voltar")

    escrever(332, 35, "Meu Perfil ✧", 27, True)
    escrever(332, 79, "Edite suas informações e conte um pouco sobre você.", 12, False, "#72646A")

    criar_cartao(312, 136, 952, 180)
    tela_perfil.create_oval(334, 160, 448, 274, fill="#E5C4C5", outline="")
    tela_perfil.create_oval(370, 179, 412, 220, fill="#FFF8F5", outline="")
    tela_perfil.create_oval(349, 224, 433, 271, fill="#FFF8F5", outline="")
    foto_na_tela = [None]
    foto_atual = [""] #guarda o caminho da foto pra salvar no banco

    escrever(486, 159, "Nome", 11, True)
    desenho_arredondado(486, 180, 350, 35, 17, cor_borda)
    desenho_arredondado(487, 181, 348, 33, 16, cor_campo)
    escrever(503, 190, usuario_logado["nome"], 11, False, cor_texto)

    escrever(860, 159, "Cidade", 11, True)
    campo_cidade = criar_campo(860, 180, 373)

    escrever(486, 240, "Usuário", 11, True)
    desenho_arredondado(486, 261, 350, 35, 17, cor_borda)
    desenho_arredondado(487, 262, 348, 33, 16, cor_campo)
    escrever(503, 270, "@" + usuario_logado["usuario"], 11, False, cor_texto)

    escrever(860, 240, "Minha frase ✨", 11, True)
    campo_frase = criar_campo(860, 261, 373)

    def mostrar_foto(caminho):
        if not caminho or not os.path.isfile(caminho):
            return

        try:
            tamanho = 110
            imagem = Image.open(caminho).convert("RGBA")
            imagem = ImageOps.fit(imagem, (tamanho, tamanho), method=Image.Resampling.LANCZOS) #essa parte aq ajusta a foto pra caber no perfil ( demorei anos pra descobrir isso afff)

            mascara = Image.new("L", (tamanho, tamanho), 0)
            draw = ImageDraw.Draw(mascara)
            draw.ellipse((0, 0, tamanho - 1, tamanho - 1), fill=255)
            imagem.putalpha(mascara)
            foto = ImageTk.PhotoImage(imagem)

            if foto_na_tela[0] is not None:
                tela_perfil.delete(foto_na_tela[0])

            foto_na_tela[0] = tela_perfil.create_image(391, 217, image=foto)
            janela_Perfil.foto_usuario = foto

        except (OSError, ValueError, tk.TclError) as erro:
            print("Erro ao abrir a foto:", erro)
            messagebox.showwarning(
                "Bloomie", "Não foi possível abrir a foto escolhida.", parent=janela_Perfil
            )

    #abre uma janelinha pra ajustar a foto antes de salvar
    def editar_foto(caminho):
        editor = tk.Toplevel(janela_Perfil)
        editor.title("Bloomie - Ajustar foto")
        editor.geometry("500x550")
        editor.resizable(False, False)
        editor.configure(bg="#FFF7F3")

        imagem_original = Image.open(caminho).convert("RGBA")

        tela_foto = tk.Canvas(
            editor,
            width=300,
            height=300,
            bg="#FFF7F3",
            highlightthickness=0
        )
        tela_foto.place(x=100, y=65)

        imagem_previa = ImageOps.fit(
            imagem_original,
            (280, 280),
            method=Image.Resampling.LANCZOS
        )

        foto_previa = ImageTk.PhotoImage(imagem_previa)
        item_foto = tela_foto.create_image(150, 150, image=foto_previa)
        tela_foto.imagem = foto_previa

        tela_foto.create_oval(
            10, 10, 290, 290,
            outline="#B98591",
            width=3
        )

        zoom = tk.DoubleVar(value=1.0)
        posicao = {"x": 0, "y": 0}
        mouse = {"x": 0, "y": 0}

        def atualizar_zoom(valor):
            escala = float(valor)
            imagem_base = ImageOps.fit(
                imagem_original,
                (280, 280),
                method=Image.Resampling.LANCZOS
            )
            novo_tamanho = round(280 * escala)
            imagem_zoom = imagem_base.resize(
                (novo_tamanho, novo_tamanho),
                Image.Resampling.LANCZOS
            )

            foto_atualizada = ImageTk.PhotoImage(imagem_zoom)
            tela_foto.itemconfig(item_foto, image=foto_atualizada)
            tela_foto.imagem = foto_atualizada

            posicao["x"] = 0
            posicao["y"] = 0
            tela_foto.coords(item_foto, 150, 150)

        barra_zoom = tk.Scale(
            editor,
            from_=1.0,
            to=3.0,
            resolution=0.1,
            orient="horizontal",
            variable=zoom,
            command=atualizar_zoom,
            label="Ajustar tamanho da foto",
            bg="#FFF7F3",
            highlightthickness=0,
            length=300
        )
        barra_zoom.place(x=100, y=385)

        def iniciar_arrasto(evento):
            mouse["x"] = evento.x
            mouse["y"] = evento.y

        def arrastar_foto(evento):
            dx = evento.x - mouse["x"]
            dy = evento.y - mouse["y"]

            limite = (round(280 * zoom.get()) - 280) / 2

            novo_x = max(-limite, min(limite, posicao["x"] + dx))
            novo_y = max(-limite, min(limite, posicao["y"] + dy))

            posicao["x"] = novo_x
            posicao["y"] = novo_y

            tela_foto.coords(item_foto, 150 + novo_x, 150 + novo_y)
            mouse["x"] = evento.x
            mouse["y"] = evento.y

        tela_foto.bind("<Button-1>", iniciar_arrasto)
        tela_foto.bind("<B1-Motion>", arrastar_foto)

        def salvar_foto():
            escala = zoom.get()
            imagem_base = ImageOps.fit(
                imagem_original,
                (280, 280),
                method=Image.Resampling.LANCZOS
            )

            tamanho_zoom = round(280 * escala)
            imagem_zoom = imagem_base.resize(
                (tamanho_zoom, tamanho_zoom),
                Image.Resampling.LANCZOS
            )

            esquerda = round((tamanho_zoom - 280) / 2 - posicao["x"])
            cima = round((tamanho_zoom - 280) / 2 - posicao["y"])

            imagem_final = imagem_zoom.crop((
                esquerda, cima,
                esquerda + 280, cima + 280
            ))

            #cria a pasta pra guardar as fotos se ela não existir
            os.makedirs(
                os.path.join(PASTA_PROJETO, "fotos_bloomie"),
                exist_ok=True
            )

            destino = os.path.join(
                PASTA_PROJETO,
                "fotos_bloomie",
                f"perfil_{usuario_logado['id']}.png"
            )

            imagem_final.save(destino)
            foto_atual[0] = destino
            mostrar_foto(destino)
            editor.destroy()

        tk.Button(
            editor, text="Salvar foto", command=salvar_foto,
            bg="#B98591", fg="white", activebackground="#A87380",
            activeforeground="white", relief="flat", borderwidth=0
        ).place(x=100, y=475, width=140, height=40)

        tk.Button(
            editor, text="Cancelar", command=editor.destroy,
            bg="#E8D6D2", fg="#713D4D", activebackground="#D9C2BD",
            activeforeground="#713D4D", relief="flat", borderwidth=0
        ).place(x=260, y=475, width=140, height=40)

    def escolher_foto():
        try:
            caminho = filedialog.askopenfilename(
                parent=janela_Perfil,
                title="Escolher foto de perfil",
                filetypes=[("Imagens", "*.png *.jpg *.jpeg *.gif"), ("Todos os arquivos", "*.*")]
            )

            if not caminho:
                return

            editar_foto(caminho)

        except (OSError, tk.TclError) as erro:
            messagebox.showerror("Bloomie", str(erro), parent=janela_Perfil)

    criar_botao(340, 277, 105, 29, "Alterar foto", escolher_foto, tag="botao_foto")


    criar_cartao(312, 328, 952, 127)
    escrever(337, 339, "▤  Sobre mim", 11, True)
    campo_sobre = criar_area_texto(335, 368, 906, 72, 300)

    criar_cartao(312, 467, 466, 112)
    escrever(335, 478, "⌁  O que quero aprender", 11, True)
    campo_aprender = criar_area_texto(335, 503, 420, 63, 200)

    criar_cartao(798, 467, 466, 112)
    escrever(820, 478, "✧  Meus interesses", 11, True)
    campo_interesses = criar_area_texto(821, 503, 419, 63, 200)

    criar_cartao(312, 592, 466, 112)
    escrever(335, 603, "◷  Disponibilidade", 11, True)
    campo_disponibilidade = criar_area_texto(335, 628, 420, 63, 200)

    criar_cartao(798, 592, 466, 112)
    escrever(820, 603, "♧  Como prefiro aprender", 11, True)
    desenho_arredondado(821, 633, 419, 42, 19, cor_borda, tag="opcao_aprender")
    desenho_arredondado(822, 634, 417, 40, 18, cor_campo, tag="opcao_aprender")

    forma_aprender = tk.StringVar(value="Selecione uma opção") #guarda a opção escolhida pelo usuário
    texto_escolha = tela_perfil.create_text(
        841, 654, text="Selecione uma opção", font=("Arial", 11),
        fill=cor_texto, anchor="w", tags="opcao_aprender"
    )
    tela_perfil.create_text(
        1211, 654, text="⌄", font=("Arial", 16, "bold"),
        fill=rosa_escuro, tags="opcao_aprender"
    )

    def selecionar_forma(opcao):
        forma_aprender.set(opcao)
        tela_perfil.itemconfig(texto_escolha, text=opcao)

    def abrir_opcoes():
        menu = tk.Menu(
            janela_Perfil, tearoff=0, bg=cor_campo,
            fg=rosa_escuro, activebackground=rosa_claro,
            activeforeground=rosa_escuro
        ) #cria a lista de opções quando o usuário clicar
        for opcao in ("Online", "Presencial", "Online e presencial"):
            menu.add_command(
                label=opcao, command=lambda escolha=opcao: selecionar_forma(escolha)
            )
        menu.tk_popup(
            janela_Perfil.winfo_rootx() + 824,
            janela_Perfil.winfo_rooty() + 675
        )
        menu.grab_release()

    tela_perfil.tag_bind("opcao_aprender", "<Button-1>", lambda evento: abrir_opcoes())
    tela_perfil.tag_bind("opcao_aprender", "<Enter>", lambda evento: tela_perfil.config(cursor="hand2"))
    tela_perfil.tag_bind("opcao_aprender", "<Leave>", lambda evento: tela_perfil.config(cursor=""))
    tela_perfil.tag_bind("opcao_aprender", "<Button-3>", lambda evento: abrir_opcoes())


    cursor.execute(
        """SELECT sobre_mim, quero_aprender, frase, cidade,
                  disponibilidade, forma_aprender, interesses, foto
           FROM perfis WHERE usuario_id = ?""",
        (usuario_logado["id"],)
    )
    dados = cursor.fetchone()

    if dados:
        sobre_mim, quero_aprender, frase, cidade, horarios, forma, gostos, foto = dados
        campo_sobre.insert("1.0", sobre_mim or "")
        campo_aprender.insert("1.0", quero_aprender or "")
        campo_frase.insert(0, frase or "")
        campo_cidade.insert(0, cidade or "")
        campo_disponibilidade.insert("1.0", horarios or "")
        campo_interesses.insert("1.0", gostos or "")

        if forma in ("Online", "Presencial", "Online e presencial"):
            selecionar_forma(forma)

        foto_atual[0] = foto or ""
        mostrar_foto(foto_atual[0])

    for campo in (campo_sobre, campo_aprender, campo_interesses, campo_disponibilidade):
        campo.contar_caracteres()


    def salvar_perfil():
        valores = (
            campo_sobre.get("1.0", "end-1c").strip(),
            campo_aprender.get("1.0", "end-1c").strip(),
            campo_frase.get().strip(),
            campo_cidade.get().strip(),
            campo_disponibilidade.get("1.0", "end-1c").strip(),
            forma_aprender.get() if forma_aprender.get() != "Selecione uma opção" else "",
            campo_interesses.get("1.0", "end-1c").strip(),
            foto_atual[0]
        ) #guarda as informações em uma tupla antes de salvar

        cursor.execute(
            "SELECT id FROM perfis WHERE usuario_id = ?",
            (usuario_logado["id"],)
        )

        if cursor.fetchone():
            cursor.execute(
                """UPDATE perfis SET
                    sobre_mim = ?, quero_aprender = ?, frase = ?, cidade = ?,
                    disponibilidade = ?, forma_aprender = ?, interesses = ?, foto = ?
                   WHERE usuario_id = ?""",
                valores + (usuario_logado["id"],)
            )

        else:
            cursor.execute(
                """INSERT INTO perfis
                    (sobre_mim, quero_aprender, frase, cidade,
                     disponibilidade, forma_aprender, interesses, foto, usuario_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                valores + (usuario_logado["id"],)
            )

        conexao.commit()
        #só recebe as moedas quando preencher as informações principais
        if valores[0] and valores[1] and valores[3] and valores[6]:
            ganhou = dar_recompensa(usuario_logado["id"], "perfil_completo", 5)
            if ganhou:
                messagebox.showinfo("Missões Bloomie 🌸", "Perfil completo! Você ganhou 5 BloomCoins.", parent=janela_Perfil)
        messagebox.showinfo("Bloomie 🌸", "Perfil salvo com sucesso!", parent=janela_Perfil)

    def limpar_campos():
        confirmacao = messagebox.askyesno(
            "Bloomie", "Limpar os campos? As alterações não salvas serão perdidas.",
            parent=janela_Perfil
        )

        if not confirmacao:
            return

        for campo in (campo_sobre, campo_aprender, campo_interesses, campo_disponibilidade):
            campo.delete("1.0", "end")

        campo_frase.delete(0, "end")
        campo_cidade.delete(0, "end")
        selecionar_forma("Selecione uma opção")

    criar_botao(614, 725, 236, 50, "▣  Salvar perfil", salvar_perfil, tag="botao_salvar")
    criar_botao(870, 725, 236, 50, "↶  Limpar campos", limpar_campos, cor="#F6DFDC", texto_cor=rosa_escuro, tag="botao_limpar")


    campo_cidade.bind("<Return>", lambda evento: campo_frase.focus_set())
    campo_frase.bind("<Return>", lambda evento: campo_sobre.focus_set())

    for campo in (campo_sobre, campo_aprender, campo_interesses, campo_disponibilidade):
        campo.bind("<Control-Return>", lambda evento: (salvar_perfil(), "break")[1]) #ctrl + enter salva sem criar outra linha

    campo_cidade.focus_set()


def abrir_tela_principal(nome_usuario):
    janela_Principal = tk.Toplevel(janela) 
    janela_Principal.title("Bloomie - Minha Conta")
    janela_Principal.geometry("900x700")
    janela_Principal.resizable(False, False)

    imagem_principal = carregar_fundo("fundo_bloomie_funcionalidades.gif", 900, 700)

    janela_Principal.imagem_principal = imagem_principal

    fundo_principal = tk.Canvas(
        janela_Principal,
        width=900,
        height=700,
        highlightthickness=0,
        borderwidth=0
    )

    fundo_principal.pack()

    fundo_principal.create_image(
        0, 0,
        image=imagem_principal,
        anchor="nw"
    ) 

    fundo_principal.create_text(
        450, 95,
        text="Seu espaço Bloomie",
        font=("Arial", 26, "bold"),
        fill="#713D4D"
    )

    fundo_principal.create_text(
        450, 170,
        text=f"Olá, {nome_usuario}!",
        font=("Arial", 23, "bold"),
        fill="#8A626A"
    )

    fundo_principal.create_text(
        450, 210,
        text="Que bom ter você aqui!",
        font=("Arial", 13),
        fill="#555555"
    )

    fundo_principal.create_text(
        450, 270,
        text="O que você deseja fazer hoje?",
        font=("Arial", 14, "bold"),
        fill="#555555"
    )


    fundo_principal.create_text(
        795, 45,
        text="⚙ Configurações",
        font=("Arial", 11, "bold"),
        fill="#536B5C",
        tags="config_inicio"
    )
    fundo_principal.tag_bind(
        "config_inicio", "<Button-1>",
        lambda evento: abrir_configuracoes()
    )

    def botao_principal(y, texto, cor, tag, comando):
        fundo_principal.create_oval(
            285, y, 335, y + 50,
            fill=cor, outline="", tags=tag
        )
        fundo_principal.create_oval(
            565, y, 615, y + 50,
            fill=cor, outline="", tags=tag
        )
        fundo_principal.create_rectangle(
            310, y, 590, y + 50,
            fill=cor, outline="", tags=tag
        )
        fundo_principal.create_text(
            450, y + 25, text=texto,
            font=("Arial", 12, "bold"),
            fill="white", tags=tag
        )
        fundo_principal.tag_bind(tag, "<Button-1>", lambda evento: comando())

    botao_principal(
        310, "⌕ Explorar habilidades", "#89998B",
        "explorar_habilidades", abrir_explorar_habilidades
    )
    botao_principal(
        370, "🌿 Compartilhar habilidade", "#B98591",
        "compartilhar_habilidade", compartilhar_habilidade
    )
    botao_principal(
        430, "🌿 Minhas habilidades", "#89998B",
        "minhas_habilidades", abrir_minhas_habilidades
    )
    botao_principal(
        490, "🌸 Meu Perfil", "#B69B89",
        "meu_perfil", abrir_meu_perfil
    )


    def cartao_destaque(x, titulo, descricao, icone, cor, tag, comando):
        y = 568
        largura = 213
        altura = 100
        raio = 22

        def arredondado(pos_x, pos_y, larg, alt, cor_fundo):
            opcoes = {"fill": cor_fundo, "outline": "", "tags": tag}

            fundo_principal.create_oval(
                pos_x, pos_y, pos_x + raio * 2, pos_y + raio * 2, **opcoes
            )
            fundo_principal.create_oval(
                pos_x + larg - raio * 2, pos_y,
                pos_x + larg, pos_y + raio * 2, **opcoes
            )
            fundo_principal.create_oval(
                pos_x, pos_y + alt - raio * 2,
                pos_x + raio * 2, pos_y + alt, **opcoes
            )
            fundo_principal.create_oval(
                pos_x + larg - raio * 2, pos_y + alt - raio * 2,
                pos_x + larg, pos_y + alt, **opcoes
            )
            fundo_principal.create_rectangle(
                pos_x + raio, pos_y,
                pos_x + larg - raio, pos_y + alt, **opcoes
            )
            fundo_principal.create_rectangle(
                pos_x, pos_y + raio,
                pos_x + larg, pos_y + alt - raio, **opcoes
            )

        arredondado(x, y, largura, altura, "#D8CCC9")
        arredondado(x + 2, y + 2, largura - 4, altura - 4, cor)

        fundo_principal.create_text(
            x + 33, y + 50, text=icone,
            font=("Arial", 25), fill="#657565", tags=tag
        )
        if tag == "cartao_jardim":
            posicao_titulo = y + 30
            posicao_descricao = y + 79
            tamanho_titulo = 11
        else:
            posicao_titulo = y + 36
            posicao_descricao = y + 63
            tamanho_titulo = 12

        fundo_principal.create_text(
            x + 61, posicao_titulo, text=titulo,
            font=("Arial", tamanho_titulo, "bold"), fill="#536B5C",
            anchor="w", tags=tag
        )
        texto_descricao = fundo_principal.create_text(
            x + 61, posicao_descricao, text=descricao,
            font=("Arial", 9), fill="#766B6D",
            anchor="w", tags=tag
        )
        

        fundo_principal.tag_bind(tag, "<Button-1>", lambda evento: comando())

        fundo_principal.tag_bind(
            tag, "<Enter>",
            lambda evento: fundo_principal.config(cursor="hand2")
        )
        fundo_principal.tag_bind(
            tag, "<Leave>",
            lambda evento: fundo_principal.config(cursor="")
        )

        return texto_descricao

    cartao_destaque(
        88, "BloomMatch", "Encontre conexões", "♡",
        "#E9EEE7", "cartao_match", abrir_bloommatch
    )

    saldo = consultar_saldo(usuario_logado["id"])

    texto_saldo = cartao_destaque(
        344, "BloomCoins", f"Seu saldo: {saldo} moedas", "◉",
        "#F4E6E8", "cartao_coins", abrir_bloomcoins
    )

    cartao_destaque(
        600, "Jardim de\nConquistas", "Suas conquistas", "🌱",
        "#E9EEE7", "cartao_jardim", abrir_jardim_conquistas
    )

    def atualizar_saldo_cartao(evento=None):
        if usuario_logado is not None:
            saldo_atual = consultar_saldo(usuario_logado["id"])

            fundo_principal.itemconfig(
                texto_saldo, text=f"Seu saldo: {saldo_atual} moedas"
            )
    janela_Principal.bind("<FocusIn>", atualizar_saldo_cartao)
    return janela_Principal

def abrir_tela_login():
    janela_Login = tk.Toplevel(janela) 
    janela_Login.title("Bloomie - Login")
    janela_Login.geometry("1000x700")
    janela_Login.resizable(False, False)

    imagem_Login = carregar_fundo("fundo_bloomie_compartilhe(2).gif", 1000, 700)

    janela_Login.imagem_Login = imagem_Login

    fundo_Login = tk.Canvas(
        janela_Login,
        width=1000,
        height=700,
        highlightthickness=0,
        borderwidth=0
    )

    fundo_Login.pack()

    fundo_Login.create_image(
        0, 0,
        image=imagem_Login,
        anchor="nw"
    ) 

    fundo_Login.create_text(
        500, 285,
        text="Entre na sua conta",
        font=("Arial", 19, "bold"),
        fill="#526653"
    )

    fundo_Login.create_text(
        500, 350,
        text="Usuário:",
        font=("Arial", 12),
        fill="#333333"
    )

    fundo_campo(fundo_Login, 364, 365, 272, 45)

    entrada_usuario = tk.Entry(
        janela_Login,
        font=("Arial", 12),
        width=28,
        justify="center",
        bg="#FFF7F3", relief="flat", bd=0, fg="#594C50"
    ) #entry cria uma caixa pra o usurio digitar, width define a largura, justify define como texto digitado fica alinhado dentro da caixa

    entrada_usuario.place(
        x=378,
        y=375,
        width=244, height=29
    )

    fundo_Login.create_text(
        500, 430,
        text="Senha:",
        font=("Arial", 12),
        fill="#333333"
    )

    fundo_campo(fundo_Login, 364, 445, 272, 45)

    entrada_senha = tk.Entry(
        janela_Login,
        font=("Arial", 12),
        width=28,
        justify="center",
        show="*", bg="#FFF7F3", relief="flat", bd=0, fg="#594C50"
    )

    entrada_senha.place(
        x=378,
        y=455,
        width=210, height=29
    )
    visibilidade_login = [False]
    botao_ver_login = tk.Button(
        janela_Login, text="◉", font=("Arial", 10), bg="#E9D8D3", fg="#713D4D",
        relief="flat", bd=0, cursor="hand2"
    )
    def alternar_senha_login():
        visibilidade_login[0] = not visibilidade_login[0]
        entrada_senha.configure(show="" if visibilidade_login[0] else "*")
        botao_ver_login.configure(text="◌" if visibilidade_login[0] else "◉")
    botao_ver_login.configure(command=alternar_senha_login)
    botao_ver_login.place(x=590, y=455, width=32, height=29)


    texto_resultado = fundo_Login.create_text(
        500, 505,
        text="",
        font=("Arial", 10),
        fill="red"
    )


    def realizar_Login():
        global usuario_logado

        usuario = entrada_usuario.get()
        senha = entrada_senha.get()

        if usuario == "" or senha == "":
            fundo_Login.itemconfig(
                texto_resultado,
                text="Preencha o usuário e a senha.",
                fill="red"
            )
            return

        cursor.execute(
            "SELECT id, nome, senha_hash FROM usuarios WHERE usuario = ?",
            (usuario,)
        ) #procura o usuário digitado no banco

        resultado = cursor.fetchone()

        if resultado is None:
            fundo_Login.itemconfig(
                texto_resultado,
                text="Usuário não encontrado. Crie uma conta primeiro.",
                fill="red"
            )

        elif verificar_senha(senha, resultado[2]):
            cursor.execute(
                "INSERT OR IGNORE INTO bloomcoins (usuario_id, saldo) VALUES (?, ?)", #não dá o bônus de novo se a conta já tiver moedas
                (resultado[0], 20)
            )
            if cursor.rowcount == 1:
                cursor.execute(
                    "INSERT INTO historico_bloomcoins (usuario_id, quantidade, motivo) VALUES (?, ?, ?)",
                    (resultado[0], 20, "Boas-vindas")
                )
            conexao.commit()

            usuario_logado = {
                "id": resultado[0],
                "nome": resultado[1],
                "usuario": usuario
            }

            salvar_sessao(usuario_logado["id"])

            janela.withdraw()
            abrir_tela_principal(resultado[1])
            janela_Login.destroy()

        else:
            fundo_Login.itemconfig(
                texto_resultado,
                text="Senha incorreta.",
                fill="red"
            )


    entrada_usuario.bind("<Return>", lambda evento: (entrada_senha.focus_set(), "break")[1])
    entrada_senha.bind("<Return>", lambda evento: (realizar_Login(), "break")[1])

    def abrir_tela_cadastro():
        janela_Cadastro = tk.Toplevel(janela_Login) 
        janela_Cadastro.title("Bloomie - Cadastro")
        janela_Cadastro.geometry("1000x700")
        janela_Cadastro.resizable(False, False)

        imagem_Cadastro = carregar_fundo("fundo_bloomie_compartilhe(2).gif", 1000, 700)

        janela_Cadastro.imagem_Cadastro = imagem_Cadastro

        fundo_Cadastro = tk.Canvas(
            janela_Cadastro,
            width=1000,
            height=700,
            highlightthickness=0,
            borderwidth=0
        )

        fundo_Cadastro.pack()

        fundo_Cadastro.create_image(
            0, 0,
            image=imagem_Cadastro,
            anchor="nw"
        ) 

        fundo_Cadastro.create_text(
            500, 270,
            text="🌸 Cadastre-se 🌸",
            font=("Arial", 20, "bold"),
            fill="#526653"
        )

        fundo_Cadastro.create_text(
            500, 330,
            text="Nome:",
            font=("Arial", 12),
            fill="#333333"
        )

        fundo_campo(fundo_Cadastro, 364, 345, 272, 45)

        entrada_nome = tk.Entry(
            janela_Cadastro,
            font=("Arial", 12),
            width=28,
            justify="center",
            bg="#FFF7F3", fg="#594C50", relief="flat", bd=0
        )

        entrada_nome.place(
            x=378,
            y=355,
            width=244, height=29
        )

        fundo_Cadastro.create_text(
            500, 410,
            text="Usuário:",
            font=("Arial", 12),
            fill="#333333"
        )

        fundo_campo(fundo_Cadastro, 364, 425, 272, 45)

        entrada_usuario_cadastro = tk.Entry(
            janela_Cadastro,
            font=("Arial", 12),
            width=28,
            justify="center",
            bg="#FFF7F3", fg="#594C50", relief="flat", bd=0
        )

        entrada_usuario_cadastro.place(
            x=378,
            y=435,
            width=244, height=29
        )

        fundo_Cadastro.create_text(
            500, 490,
            text="Senha:",
            font=("Arial", 12),
            fill="#333333"
        )

        fundo_campo(fundo_Cadastro, 364, 505, 272, 45)

        entrada_senha_cadastro = tk.Entry(
            janela_Cadastro,
            font=("Arial", 12),
            width=28,
            justify="center",
            bg="#FFF7F3", fg="#594C50", relief="flat", bd=0,
            show="*"
        )

        entrada_senha_cadastro.place(
            x=378,
            y=515,
            width=210, height=29
        )
        visibilidade_cadastro = [False]
        botao_ver_cadastro = tk.Button(
            janela_Cadastro, text="◉", font=("Arial", 10), bg="#E9D8D3", fg="#713D4D",
            relief="flat", bd=0, cursor="hand2"
        )
        def alternar_senha_cadastro():
            visibilidade_cadastro[0] = not visibilidade_cadastro[0]
            entrada_senha_cadastro.configure(show="" if visibilidade_cadastro[0] else "*")
            botao_ver_cadastro.configure(text="◌" if visibilidade_cadastro[0] else "◉")
        botao_ver_cadastro.configure(command=alternar_senha_cadastro)
        botao_ver_cadastro.place(x=590, y=515, width=32, height=29)

        texto_resultado_cadastro = fundo_Cadastro.create_text(
            500, 565,
            text="",
            font=("Arial", 10),
            fill="red"
        )


        def realizar_Cadastro():
            global usuario_logado

            nome = entrada_nome.get().strip()
            usuario = entrada_usuario_cadastro.get().strip()
            senha = entrada_senha_cadastro.get()

            if nome == "" or usuario == "" or senha == "":
                fundo_Cadastro.itemconfig(
                    texto_resultado_cadastro,
                    text="Preencha todos os campos!",
                    fill="red"
                )
                return

            #a frase pode substituir o código de recuperação caso ele seja perdido
            senha_protegida = proteger_senha(senha)

            try:
                cursor.execute(
                    "INSERT INTO usuarios (nome, usuario, senha_hash, frase_seguranca_hash) VALUES (?, ?, ?, NULL)",
                    (nome, usuario, senha_protegida)
                )

                novo_usuario = cursor.lastrowid #pega o id da conta que acabou de ser criada

                cursor.execute(
                    "INSERT INTO bloomcoins (usuario_id, saldo) VALUES (?, ?)",
                    (novo_usuario, 20)
                )
                cursor.execute(
                    "INSERT INTO historico_bloomcoins (usuario_id, quantidade, motivo) VALUES (?, ?, ?)",
                    (novo_usuario, 20, "Boas-vindas")
                )

                conexao.commit() #salva o cadastro no banco

                usuario_logado = {
                    "id": novo_usuario,
                    "nome": nome,
                    "usuario": usuario
                } #entra na conta logo depois do cadastro

                salvar_sessao(usuario_logado["id"])

                janela_Cadastro.destroy()
                janela_Login.destroy()
                janela.withdraw()
                painel = abrir_tela_principal(nome)
                #mostra o código de recuperação uma vez, para guardar sem e-mail
                messagebox.showinfo(
                    "Bloomie", "DEFINA UMA FRASE DE SEGURANÇA", parent=painel
                )
                abrir_configuracoes(definir_frase=True)

            except sqlite3.IntegrityError:
                fundo_Cadastro.itemconfig(
                    texto_resultado_cadastro,
                    text="Esse nome de usuário já existe!",
                    fill="red"
                )



        entrada_nome.bind("<Return>", lambda event: (entrada_usuario_cadastro.focus_set(), "break")[1])
        entrada_usuario_cadastro.bind("<Return>", lambda event: (entrada_senha_cadastro.focus_set(), "break")[1])
        entrada_senha_cadastro.bind("<Return>", lambda event: (realizar_Cadastro(), "break")[1])
        entrada_nome.focus_set()


        fundo_Cadastro.create_oval(
            375, 600,
            415, 640,
            fill="#89998B",
            outline="",
            tags="botao_criar_conta"
        )

        fundo_Cadastro.create_oval(
            585, 600,
            625, 640,
            fill="#89998B",
            outline="",
            tags="botao_criar_conta"
        )

        fundo_Cadastro.create_rectangle(
            395, 600,
            605, 640,
            fill="#89998B",
            outline="",
            tags="botao_criar_conta"
        ) 

        fundo_Cadastro.create_text(
            460, 620,
            text="❀",
            font=("Segoe UI Symbol", 17),
            fill="white",
            tags="botao_criar_conta"
        )

        fundo_Cadastro.create_text(
            520, 620,
            text="Criar conta",
            font=("Arial", 11, "bold"),
            fill="white",
            tags="botao_criar_conta"
        )

        fundo_Cadastro.tag_bind(
            "botao_criar_conta",
            "<Button-1>",
            lambda event: realizar_Cadastro()
        )


    entrada_usuario.bind("<Return>", lambda event: entrada_senha.focus_set())
    entrada_senha.bind("<Return>", lambda event: realizar_Login())
    entrada_usuario.focus_set()


    fundo_Login.create_text(
        500, 527, text="Esqueci minha senha",
        font=("Arial", 10, "underline"), fill="#713D4D", tags="esqueci_senha"
    )
    fundo_Login.tag_bind(
        "esqueci_senha", "<Button-1>",
        lambda evento: abrir_recuperacao_senha(janela_Login)
    )

    botao_login = botao_suave(
        janela_Login, "Entrar", realizar_Login,
        largura=230, cor="#89998B"
    )
    botao_login.place(x=385, y=550)

    botao_cadastro = botao_suave(
        janela_Login, "Criar conta", abrir_tela_cadastro,
        largura=230, cor="#89998B"
    )
    botao_cadastro.place(x=385, y=605)

def abrir_tela_informativa(nome, titulo, frase, explicacao, encerramento,
                          cor_titulo, cor_encerramento, cor_botao):
    janela_info = tk.Toplevel(janela)
    janela_info.title(f"Bloomie - {nome}")
    janela_info.geometry("1000x700")
    janela_info.resizable(False, False)

    imagem = carregar_fundo("fundo_bloomie_compartilhe(2).gif", 1000, 700)
    janela_info.imagem_fundo = imagem

    fundo = tk.Canvas(
        janela_info, width=1000, height=700,
        highlightthickness=0, borderwidth=0
    )
    fundo.pack()
    fundo.create_image(0, 0, image=imagem, anchor="nw")

    fundo.create_text(
        500, 285, text=titulo,
        font=("Arial", 25, "bold"), fill=cor_titulo
    )
    fundo.create_text(
        500, 350, text=frase,
        font=("Arial", 14, "bold"), fill="#555555"
    )
    fundo.create_text(
        500, 415, text=explicacao,
        font=("Arial", 12), fill="#666666", justify="center"
    )
    fundo.create_text(
        500, 515, text=encerramento,
        font=("Arial", 12, "bold"), fill=cor_encerramento
    )

    fundo.create_oval(
        390, 565, 435, 610,
        fill=cor_botao, outline="", tags="voltar"
    )
    fundo.create_oval(
        565, 565, 610, 610,
        fill=cor_botao, outline="", tags="voltar"
    )
    fundo.create_rectangle(
        412, 565, 588, 610,
        fill=cor_botao, outline="", tags="voltar"
    )
    fundo.create_text(
        500, 587, text="← Voltar",
        font=("Arial", 12, "bold"), fill="white", tags="voltar"
    )
    fundo.tag_bind("voltar", "<Button-1>", lambda evento: janela_info.destroy())


def clicar_aprenda():
    abrir_tela_informativa(
        "Aprenda",
        "✦ Aprenda",
        "Sempre existe algo novo para descobrir.",
        "No Bloomie você pode conhecer habilidades e conhecimentos\n"
        "compartilhados por outras pessoas.\n\n"
        "Explore novos interesses, descubra coisas que gostaria\n"
        "de aprender e encontre pessoas que podem ajudar você.",
        "Descubra. Aprenda. Evolua. ✦",
        "#8A626A", "#B98591", "#B98591"
    )


def clicar_compartilhe():
    abrir_tela_informativa(
        "Compartilhe",
        "♡ Compartilhe",
        "Todo mundo tem algo que sabe fazer.",
        "No Bloomie você pode compartilhar suas habilidades,\n"
        "experiências e conhecimentos com outras pessoas.\n\n"
        "Aquilo que parece simples para você pode ser exatamente\n"
        "o que outra pessoa está procurando aprender.",
        "Ensine. Compartilhe. Conecte-se. 🌿",
        "#4F5D4D", "#7D8F78", "#89998B"
    )


def clicar_cresca():
    abrir_tela_informativa(
        "Cresça",
        "✧ Cresça",
        "Cada nova habilidade é uma nova possibilidade.",
        "No Bloomie você pode acompanhar seu desenvolvimento,\n"
        "descobrir novas habilidades e perceber sua evolução.\n\n"
        "Aprender, compartilhar e trocar experiências pode abrir\n"
        "novas oportunidades e ajudar você a crescer cada vez mais.",
        "Aprenda. Evolua. Cresça. ✧",
        "#8A6F5D", "#B69B89", "#B69B89"
    )


imagem_fundo = carregar_fundo("fundo_bloomie_painel.gif", 1300, 800)


tela = tk.Canvas(
    janela,
    width=1300,
    height=800,
    highlightthickness=0,
    borderwidth=0
)


tela.pack()


tela.create_image(
    0, 0,
    image=imagem_fundo,
    anchor="nw"
) 


def criar_card(x, y, cor, tag, icone, titulo, descricao):
    largura = 225
    altura = 176
    raio = 20

    tela.create_oval(
        x, y,
        x + raio * 2, y + raio * 2,
        fill=cor,
        outline="",
        tags=tag
    )

    tela.create_oval(
        x + largura - raio * 2, y,
        x + largura, y + raio * 2,
        fill=cor,
        outline="",
        tags=tag
    )

    tela.create_oval(
        x, y + altura - raio * 2,
        x + raio * 2, y + altura,
        fill=cor,
        outline="",
        tags=tag
    )

    tela.create_oval(
        x + largura - raio * 2, y + altura - raio * 2,
        x + largura, y + altura,
        fill=cor,
        outline="",
        tags=tag
    )

    tela.create_rectangle(
        x + raio, y,
        x + largura - raio, y + altura,
        fill=cor,
        outline="",
        tags=tag
    )

    tela.create_rectangle(
        x, y + raio,
        x + largura, y + altura - raio,
        fill=cor,
        outline="",
        tags=tag
    ) 

    centro = x + largura / 2

    tela.create_text(
        centro, y + 35,
        text=icone,
        font=("Arial", 20),
        fill="#555555",
        tags=tag
    )

    tela.create_text(
        centro, y + 70,
        text=titulo,
        font=("Arial", 13, "bold"),
        fill="#444444",
        tags=tag
    )

    tela.create_text(
        centro, y + 110,
        text=descricao,
        font=("Arial", 10),
        fill="#666666",
        justify="center",
        tags=tag
    )

    tela.create_text(
        centro, y + 148,
        text="→",
        font=("Arial", 16),
        fill="#777777",
        tags=tag
    )


cards = [
    (292, 442, "#F5DFDF", "aprenda", "✦", "Aprenda", "Descubra novas\nhabilidades"),
    (538, 442, "#E1E7DE", "compartilhe", "♡", "Compartilhe", "Ensine o que\nvocê sabe"),
    (783, 442, "#EEE0D7", "cresca", "✧", "Cresça", "Conquiste novas\noportunidades")
]


for card in cards:
    criar_card(*card)


tela.tag_bind(
    "aprenda",
    "<Button-1>",
    lambda event: clicar_aprenda()
)


tela.tag_bind(
    "compartilhe",
    "<Button-1>",
    lambda event: clicar_compartilhe()
)


tela.tag_bind(
    "cresca",
    "<Button-1>",
    lambda event: clicar_cresca()
) #faz os três cards responderem ao clique


tela.create_oval(
    520, 700,
    572, 752,
    fill="#89998B",
    outline="",
    tags="entrar"
)


tela.create_oval(
    728, 700,
    780, 752,
    fill="#89998B",
    outline="",
    tags="entrar"
)


tela.create_rectangle(
    546, 700,
    754, 752,
    fill="#89998B",
    outline="",
    tags="entrar"
) 


tela.create_text(
    608, 726,
    text="↪",
    font=("Arial", 30, "bold"),
    fill="white",
    tags="entrar"
)


tela.create_text(
    670, 726,
    text="Entrar",
    font=("Arial", 15, "bold"),
    fill="white",
    tags="entrar"
)


tela.tag_bind(
    "entrar",
    "<Button-1>",
    lambda event: abrir_tela_login()
) 

def recuperar_sessao():
    global usuario_logado

    cursor.execute("""
    SELECT usuarios.id, usuarios.nome, usuarios.usuario
        FROM sessao
        JOIN usuarios ON usuarios.id = sessao.usuario_id
        WHERE sessao.id = 1
    """)

    resultado = cursor.fetchone()

    if resultado:
        usuario_logado = {
         "id": resultado[0],
         "nome": resultado[1],
         "usuario": resultado[2]
        }

        janela.withdraw()
        abrir_tela_principal(resultado[1])

recuperar_sessao()

janela.mainloop() #mantém o programa funcionando enquanto a janela ta aberta