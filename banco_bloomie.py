#inicio: dia 04 de novembro(lembrar de ver se a questao da foto esta funcionando)

import sqlite3
import os

class BancoBloomie: #organiza o acesso ao banco de dados 
    def __init__(self, pasta_projeto):
        caminho = os.path.join(pasta_projeto, "bloomie.db")
        self.conexao = sqlite3.connect(caminho) #faz a conexão com o banco
        self.cursor = self.conexao.cursor() #permite executar comandos no banco

    def salvar(self):
        self.conexao.commit()

    def consultar_saldo(self, usuario_id):
        self.cursor.execute(
            "SELECT saldo FROM bloomcoins WHERE usuario_id = ?",
            (usuario_id,)
        )
        resultado = self.cursor.fetchone()
        if resultado:
            return resultado[0]
        return 0

    def consultar_historico_bloomcoins(self, usuario_id):
        self.cursor.execute(
            "SELECT quantidade, motivo, data_movimento FROM historico_bloomcoins WHERE usuario_id = ? ORDER BY id DESC LIMIT 7",
            (usuario_id,)
        )
        return self.cursor.fetchall()

    def registrar_recompensa(self, usuario_id, missao, moedas):
        try:
            self.cursor.execute(
                "INSERT OR IGNORE INTO missoes_concluidas (usuario_id, missao) VALUES (?, ?)",
                (usuario_id, missao)
            ) #ignore evita ganhar a mesma recompensa duas vezes

            if self.cursor.rowcount == 0: #zero significa que a missão já tinha sido concluída
                self.salvar()
                return False

            self.cursor.execute(
                "INSERT OR IGNORE INTO bloomcoins (usuario_id, saldo) VALUES (?, 20)",
                (usuario_id,)
            )
            self.cursor.execute(
                "UPDATE bloomcoins SET saldo = saldo + ? WHERE usuario_id = ?",
                (moedas, usuario_id)
            )
            self.cursor.execute(
                "INSERT INTO historico_bloomcoins (usuario_id, quantidade, motivo) VALUES (?, ?, ?)",
                (usuario_id, moedas, missao)
            )
            self.salvar()
            return True
        except sqlite3.Error:
            self.conexao.rollback() #desfaz as mudanças se o banco der erro
            raise

    def consultar_agendamento(self, pedido_id, usuario_id):
        self.cursor.execute("""
            SELECT aluno_id, professor_id, status, data_aula, hora_aula,
                   modalidade_aula, local_aula, situacao_agendamento,
                   pedido_alteracao, confirmado_aluno, confirmado_professor,
                   proposta_por, COALESCE(solicitado_por, aluno_id)
            FROM solicitacoes
            WHERE id = ? AND (aluno_id = ? OR professor_id = ?)
        """, (pedido_id, usuario_id, usuario_id))
        dados = self.cursor.fetchone()
        if not dados:
            return None
        campos = (
            "aluno_id", "professor_id", "status", "data_aula", "hora_aula",
            "modalidade_aula", "local_aula", "situacao_agendamento",
            "pedido_alteracao", "confirmado_aluno", "confirmado_professor",
            "proposta_por", "solicitado_por"
        )
        return dict(zip(campos, dados))

    def propor_agendamento(self, pedido_id, participante_id, data, hora, modalidade, local):
        from datetime import datetime

        data = data.strip()
        hora = hora.strip()
        modalidade = modalidade.strip().lower()
        local = local.strip()

        import re
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", data) or not re.fullmatch(r"\d{2}:\d{2}", hora):
            return "Informe a data como DD/MM/AAAA e o horário como HH:MM."
        try:
            momento = datetime.strptime(f"{data} {hora}", "%d/%m/%Y %H:%M")
        except ValueError:
            return "Informe a data como DD/MM/AAAA e o horário como HH:MM."
        if momento <= datetime.now():
            return "Escolha uma data e um horário futuros."
        if modalidade not in ("online", "presencial"):
            return "Selecione uma modalidade válida."
        if modalidade == "online" and not local:
            local = f"https://meet.jit.si/BloomieAula{pedido_id}"
        if modalidade == "presencial" and not local:
            return "Informe o endereço da aula presencial."
        if not local or len(local) > 250:
            return "Informe o link ou endereço combinado (até 250 caracteres)."
        if modalidade == "online":
            from urllib.parse import urlsplit
            endereco = urlsplit(local)
            if endereco.scheme != "https" or not endereco.hostname or endereco.username:
                return "Para aulas online, use um link HTTPS válido."

        self.cursor.execute("""
            UPDATE solicitacoes
            SET data_aula = ?, hora_aula = ?, modalidade_aula = ?, local_aula = ?,
                situacao_agendamento = 'proposta', pedido_alteracao = NULL,
                proposta_por = ?
            WHERE id = ? AND (aluno_id = ? OR professor_id = ?) AND status = 'aceita'
              AND (situacao_agendamento = 'sem_proposta'
                   OR (situacao_agendamento = 'alteracao_solicitada' AND proposta_por = ?)
                   OR (situacao_agendamento = 'proposta' AND proposta_por = ?))
              AND confirmado_aluno = 0 AND confirmado_professor = 0
        """, (data, hora, modalidade, local, participante_id,
              pedido_id, participante_id, participante_id, participante_id, participante_id))
        alterou = self.cursor.rowcount
        if alterou:
            self.salvar()
            return "Proposta enviada! Agora a outra pessoa pode aceitar ou pedir alteração."
        return "Não foi possível propor a aula para essa solicitação."

    def aceitar_agendamento(self, pedido_id, participante_id):
        self.cursor.execute("""
            UPDATE solicitacoes SET situacao_agendamento = 'confirmado',
                                    pedido_alteracao = NULL
            WHERE id = ? AND (aluno_id = ? OR professor_id = ?) AND status = 'aceita'
              AND situacao_agendamento = 'proposta'
              AND proposta_por IS NOT NULL AND proposta_por != ?
        """, (pedido_id, participante_id, participante_id, participante_id))
        alterou = self.cursor.rowcount
        if alterou:
            self.salvar()
            return "Horário confirmado! A aula está agendada."
        return "Não há uma proposta aguardando sua confirmação."

    def pedir_alteracao_agendamento(self, pedido_id, participante_id, mensagem):
        mensagem = mensagem.strip()
        if not mensagem or len(mensagem) > 250:
            return "Descreva o ajuste desejado em até 250 caracteres."

        self.cursor.execute("""
            UPDATE solicitacoes SET situacao_agendamento = 'alteracao_solicitada',
                                    pedido_alteracao = ?
            WHERE id = ? AND (aluno_id = ? OR professor_id = ?) AND status = 'aceita'
              AND situacao_agendamento = 'proposta'
              AND proposta_por IS NOT NULL AND proposta_por != ?
        """, (mensagem, pedido_id, participante_id, participante_id, participante_id))
        alterou = self.cursor.rowcount
        if alterou:
            self.salvar()
            return "Pedido de alteração enviado! Aguarde uma nova proposta."
        return "Não há uma proposta que possa ser alterada agora."

    def registrar_convite_match(self, aluno_id, professor_id, habilidade_id, novo_evento=False):
        #um convite por par; histórico antigo não impede que o match seja registrado
        if aluno_id == professor_id:
            return False
        self.cursor.execute("SELECT usuario_id FROM habilidades WHERE id = ?", (habilidade_id,))
        habilidade = self.cursor.fetchone()
        if not habilidade or habilidade[0] != professor_id:
            return False
        for quem_curtiu, dono in ((aluno_id, professor_id), (professor_id, aluno_id)):
            self.cursor.execute("""
                SELECT 1 FROM bloommatch_reacoes r
                JOIN habilidades h ON h.id = r.habilidade_id
                WHERE r.usuario_id = ? AND h.usuario_id = ? AND r.acao = 'curti'
                LIMIT 1
            """, (quem_curtiu, dono))
            if self.cursor.fetchone() is None:
                return False

        menor, maior = sorted((aluno_id, professor_id))
        self.cursor.execute("""
            INSERT OR IGNORE INTO bloommatch_convites (usuario_menor_id, usuario_maior_id)
            VALUES (?, ?)
        """, (menor, maior))
        if self.cursor.rowcount == 0 and not novo_evento:
            self.salvar()  #não cria pedidos repetidos ao abrir as telas
            return False
        #uma nova curtida explícita pode iniciar outra troca se a anterior terminou
        try:
            self.cursor.execute("""
                SELECT id FROM solicitacoes
                WHERE status IN ('pendente', 'aceita')
                  AND ((aluno_id = ? AND professor_id = ?)
                    OR (aluno_id = ? AND professor_id = ?))
                ORDER BY id DESC LIMIT 1
            """, (aluno_id, professor_id, professor_id, aluno_id))
            ativa = self.cursor.fetchone()
            if ativa:
                #já havia um pedido entre as duas pessoas: vira troca gratuita
                self.cursor.execute("""
                    UPDATE solicitacoes SET tipo = 'troca', custo_bloomcoins = 0
                    WHERE status IN ('pendente', 'aceita')
                      AND ((aluno_id = ? AND professor_id = ?)
                        OR (aluno_id = ? AND professor_id = ?))
                """, (aluno_id, professor_id, professor_id, aluno_id))
                self.salvar()
                return False

            #preserva convites de versões antigas já concluídos/recusados
            self.cursor.execute("""
                SELECT id FROM solicitacoes
                WHERE tipo = 'troca'
                  AND ((aluno_id = ? AND professor_id = ?)
                    OR (aluno_id = ? AND professor_id = ?))
                LIMIT 1
            """, (aluno_id, professor_id, professor_id, aluno_id))
            if self.cursor.fetchone() and not novo_evento:
                self.salvar()
                return False

            self.cursor.execute("""
                INSERT INTO solicitacoes
                    (aluno_id, professor_id, habilidade_id, tipo, status,
                     custo_bloomcoins, solicitado_por)
                VALUES (?, ?, ?, 'troca', 'pendente', 0, ?)
            """, (aluno_id, professor_id, habilidade_id, aluno_id))
            self.salvar()
            return True
        except sqlite3.Error:
            self.conexao.rollback()
            raise

    def sincronizar_matches_em_pedidos(self, usuario_id=None):
        #reconcilia curtidas mútuas anteriores sem repetir convites
        consulta = """
            SELECT DISTINCT r.usuario_id, h.usuario_id
            FROM bloommatch_reacoes r
            JOIN habilidades h ON h.id = r.habilidade_id
            WHERE r.acao = 'curti' AND r.usuario_id != h.usuario_id
              AND EXISTS (
                  SELECT 1 FROM bloommatch_reacoes outra
                  JOIN habilidades minha ON minha.id = outra.habilidade_id
                  WHERE outra.usuario_id = h.usuario_id
                    AND minha.usuario_id = r.usuario_id AND outra.acao = 'curti'
              )
        """
        parametros = ()
        if usuario_id is not None:
            consulta += " AND (r.usuario_id = ? OR h.usuario_id = ?)"
            parametros = (usuario_id, usuario_id)
        self.cursor.execute(consulta, parametros)
        pares = {tuple(sorted(p)) for p in self.cursor.fetchall()}
        novos = 0
        for aluno_id, professor_id in pares:
            self.cursor.execute("""
                SELECT h.id FROM bloommatch_reacoes r
                JOIN habilidades h ON h.id = r.habilidade_id
                WHERE r.usuario_id = ? AND h.usuario_id = ? AND r.acao = 'curti'
                ORDER BY h.id LIMIT 1
            """, (aluno_id, professor_id))
            achou = self.cursor.fetchone()
            if achou and self.registrar_convite_match(aluno_id, professor_id, achou[0]):
                novos += 1
        return novos

    def fechar(self):
        self.conexao.close()

    def criar_tabelas(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL
        )
        """) #cria a tabela de usuários caso ela ainda não exista

        #contas antigas continuam funcionando; o código é opcional até ser criado
        self.cursor.execute("PRAGMA table_info(usuarios)")
        colunas_usuarios = {linha[1] for linha in self.cursor.fetchall()}
        if "recuperacao_hash" not in colunas_usuarios:
            self.cursor.execute("ALTER TABLE usuarios ADD COLUMN recuperacao_hash TEXT")
        if "frase_seguranca_hash" not in colunas_usuarios:
            self.cursor.execute("ALTER TABLE usuarios ADD COLUMN frase_seguranca_hash TEXT")
        #o e-mail só fica associado à conta depois de confirmar o código
        if "email" not in colunas_usuarios:
            self.cursor.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
        if "email_verificado" not in colunas_usuarios:
            self.cursor.execute("ALTER TABLE usuarios ADD COLUMN email_verificado INTEGER NOT NULL DEFAULT 0")

        self.cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_email_verificado_unico
            ON usuarios(LOWER(email))
            WHERE email IS NOT NULL AND email_verificado = 1
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS codigos_email (
                usuario_id INTEGER NOT NULL,
                finalidade TEXT NOT NULL CHECK(finalidade IN ('vincular', 'redefinir')),
                endereco TEXT NOT NULL,
                codigo_hash TEXT NOT NULL,
                enviado_em INTEGER NOT NULL,
                expira_em INTEGER NOT NULL,
                tentativas INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (usuario_id, finalidade),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessao(
            id INTEGER PRIMARY KEY CHECK (id = 1),
            usuario_id INTEGER NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """) #pra guardar se o usuario ficou conectado

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS habilidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            habilidade TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descricao TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS perfis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL UNIQUE,
            sobre_mim TEXT,
            quero_aprender TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """) #cria a tabela que guarda as informações do perfil

        #confere se os campos do perfil já existem
        self.cursor.execute("PRAGMA table_info(perfis)")

        colunas_perfis = self.cursor.fetchall()

        nomes_colunas = []

        for coluna in colunas_perfis:
            nomes_colunas.append(coluna[1])

        if "frase" not in nomes_colunas:
            self.cursor.execute(
                "ALTER TABLE perfis ADD COLUMN frase TEXT"
            )

        if "cidade" not in nomes_colunas:
            self.cursor.execute(
                "ALTER TABLE perfis ADD COLUMN cidade TEXT"
            )

        if "disponibilidade" not in nomes_colunas:
            self.cursor.execute(
                "ALTER TABLE perfis ADD COLUMN disponibilidade TEXT"
            )

        if "forma_aprender" not in nomes_colunas:
            self.cursor.execute(
                "ALTER TABLE perfis ADD COLUMN forma_aprender TEXT"
            )

        if "interesses" not in nomes_colunas:
            self.cursor.execute(
                "ALTER TABLE perfis ADD COLUMN interesses TEXT"
            )

        if "foto" not in nomes_colunas:
            self.cursor.execute(
                "ALTER TABLE perfis ADD COLUMN foto TEXT"
            )

        #guarda as habilidades que cada usuário tem interesse
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS interesses_habilidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            habilidade_id INTEGER NOT NULL,
            UNIQUE(usuario_id, habilidade_id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (habilidade_id) REFERENCES habilidades(id)
         )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloomcoins (
            usuario_id INTEGER PRIMARY KEY,
            saldo INTEGER NOT NULL DEFAULT 20,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """) #cada usuário tem um saldo, que começa com 20 moedas

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS missoes_concluidas (
            usuario_id INTEGER NOT NULL,
            missao TEXT NOT NULL,
            data_conclusao TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, missao),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """) #guarda as missões que cada pessoa já terminou

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_bloomcoins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            quantidade INTEGER NOT NULL,
            motivo TEXT NOT NULL,
            data_movimento TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
        """) #guarda de onde vieram as moedas

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS solicitacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL, 
            professor_id INTEGER NOT NULL,
            habilidade_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            FOREIGN KEY (aluno_id) REFERENCES usuarios(id),
            FOREIGN KEY (professor_id) REFERENCES usuarios(id),
            FOREIGN KEY (habilidade_id) REFERENCES habilidades(id)
        )
        """) #guarda os pedidos de aulas entre os usuários

        self.cursor.execute("PRAGMA table_info(solicitacoes)")
        #confere quais colunas já existem na tabela de solicitações
        colunas_pedidos = [coluna[1] for coluna in self.cursor.fetchall()]

        #adiciona os campos que faltam pra registrar as aulas
        if "tipo" not in colunas_pedidos:
            self.cursor.execute("ALTER TABLE solicitacoes ADD COLUMN tipo TEXT DEFAULT 'paga'")
        if "custo_bloomcoins" not in colunas_pedidos:
            self.cursor.execute("ALTER TABLE solicitacoes ADD COLUMN custo_bloomcoins INTEGER NOT NULL DEFAULT 5")
            self.cursor.execute("UPDATE solicitacoes SET custo_bloomcoins = 0 WHERE tipo = 'troca'")
            self.cursor.execute("""
                UPDATE solicitacoes SET custo_bloomcoins = 20
                WHERE tipo = 'paga' AND status = 'concluida'
                  AND EXISTS (
                      SELECT 1 FROM historico_bloomcoins mov
                      WHERE mov.usuario_id = solicitacoes.aluno_id
                        AND mov.quantidade = -20
                        AND mov.motivo = 'Aula #' || solicitacoes.id
                  )
            """)
        if "confirmado_aluno" not in colunas_pedidos:
            self.cursor.execute("ALTER TABLE solicitacoes ADD COLUMN confirmado_aluno INTEGER DEFAULT 0")
        if "confirmado_professor" not in colunas_pedidos:
            self.cursor.execute("ALTER TABLE solicitacoes ADD COLUMN confirmado_professor INTEGER DEFAULT 0")

        #guarda a proposta de data, horário e modalidade da aula
        campos_agendamento = (
            ("data_aula", "TEXT"),
            ("hora_aula", "TEXT"),
            ("modalidade_aula", "TEXT"),
            ("local_aula", "TEXT"),
            ("situacao_agendamento", "TEXT NOT NULL DEFAULT 'sem_proposta'"),
            ("pedido_alteracao", "TEXT"),
            ("proposta_por", "INTEGER"),
            ("solicitado_por", "INTEGER")
        )
        for campo, tipo_coluna in campos_agendamento:
            if campo not in colunas_pedidos:
                self.cursor.execute(
                    f"ALTER TABLE solicitacoes ADD COLUMN {campo} {tipo_coluna}"
                )

        self.cursor.execute("""
            UPDATE solicitacoes SET proposta_por = professor_id
            WHERE proposta_por IS NULL
              AND situacao_agendamento IN ('proposta', 'alteracao_solicitada', 'confirmado')
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS sala_online_mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL,
            remetente_id INTEGER NOT NULL,
            mensagem TEXT NOT NULL,
            data_envio TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pedido_id) REFERENCES solicitacoes(id),
            FOREIGN KEY (remetente_id) REFERENCES usuarios(id)
        )
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sala_online_pedido
            ON sala_online_mensagens(pedido_id, id)
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloommatch_reacoes (
            usuario_id INTEGER NOT NULL,
            habilidade_id INTEGER NOT NULL,
            acao TEXT NOT NULL CHECK(acao IN ('curti', 'passei')),
            PRIMARY KEY (usuario_id, habilidade_id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (habilidade_id) REFERENCES habilidades(id)
        )
        """) #guarda as curtidas e os perfis que a pessoa passou

        #a criação dos pedidos agora é feita no python, não em triggers escondidos no banco
        self.cursor.execute("DROP TRIGGER IF EXISTS bloommatch_criar_solicitacao_insert")
        self.cursor.execute("DROP TRIGGER IF EXISTS bloommatch_criar_solicitacao_update")
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bloommatch_convites (
                usuario_menor_id INTEGER NOT NULL,
                usuario_maior_id INTEGER NOT NULL,
                PRIMARY KEY (usuario_menor_id, usuario_maior_id)
            )
        """)
        self.salvar()
        self.sincronizar_matches_em_pedidos()

