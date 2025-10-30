# 🗑️ Guia de Limpeza de Dados por Grupo

## 📋 Resumo

Existem **2 formas** para limpar todos os registros de agenda, procedimentos financeiros e qualidade de um grupo específico (ex: GAZO).

---

## ✅ Opção 1: Via Painel Admin (Mais Intuitivo)

Agora que melhoramos os admins com **filtros de grupo**, esta é a forma mais fácil:

### Passo a passo:

1. **Acesse o Django Admin**: `http://seu-dominio/admin`

2. **Vá para cada seção e filtre pelo grupo "GAZO":**

   **📅 Agenda → Procedimentos**
   - Na lista, clique no filtro "Group" à direita
   - Selecione "GAZO"
   - Selecione todos com o checkbox ☑️ no topo
   - Em "Action", escolha "Delete selected"
   - Confirme

   **📅 Agenda → Escalas dos Anestesiologistas**
   - Filtre por "Group" = "GAZO"
   - Selecione todos
   - Delete

   **💰 Financeiro → Procedimentos Financeiros**
   - Filtre por "Group" = "GAZO"
   - Selecione todos
   - Delete

   **💰 Financeiro → Despesas**
   - Filtre por "Group" = "GAZO"
   - Selecione todos
   - Delete

   **💰 Financeiro → Despesas Recorrentes**
   - Filtre por "Group" = "GAZO"
   - Selecione todos
   - Delete

   **⭐ Qualidade → Avaliações RPA** 
   - Não há filtro de grupo aqui, então procure pelo procedimento do GAZO
   - Ou pule para opção 2

   **⭐ Qualidade → Qualidade dos Procedimentos**
   - Não há filtro de grupo aqui, então procure pelo procedimento do GAZO
   - Ou pule para opção 2

### ⚠️ Ordem Importante:
1. Escalas (sem dependências)
2. Despesas Recorrentes (sem dependências)
3. Procedimentos (**IMPORTANTE: deleta em cascata AvaliacaoRPA + ProcedimentoQualidade**)
4. Financeiros orfãos
5. Despesas

---

## 🚀 Opção 2: Via Command Script (Automatizado - RECOMENDADO)

Esta é a forma **mais segura e rápida** para limpar TUDO de uma vez.

### Como usar:

**Abra o terminal/PowerShell no diretório do projeto:**

```bash
# Primeiro, descubra o ID do grupo GAZO
python manage.py shell
>>> from registration.models import Groups
>>> groups = Groups.objects.all()
>>> for g in groups:
...     print(f"ID: {g.id}, Nome: {g.name}")
>>> exit()
```

**Exemplo de saída:**
```
ID: 1, Nome: GAZO
ID: 2, Nome: OUTRO_GRUPO
```

### Executar o comando de limpeza:

**Opção A: Apenas visualizar o que será deletado (DRY-RUN):**
```bash
python manage.py limpar_dados_grupo 1 --dry-run
```

Saída esperada:
```
⚠️  AVISO: Você está prestes a deletar TODOS os dados do grupo: GAZO

📊 Registros a serem deletados:

  • Procedimentos: 42
  • Escalas: 15
  • Financeiro: 50
  • Despesas: 8
  • Despesas Recorrentes: 3

  TOTAL: 118 registros

✓ Modo DRY-RUN: Nenhum dado foi deletado
```

**Opção B: Deletar com confirmação interativa (RECOMENDADO):**
```bash
python manage.py limpar_dados_grupo 1
```

Saída:
```
⚠️  AVISO: Você está prestes a deletar TODOS os dados do grupo: GAZO

📊 Registros a serem deletados:

  • Procedimentos: 42
  • Escalas: 15
  • Financeiro: 50
  • Despesas: 8
  • Despesas Recorrentes: 3

  TOTAL: 118 registros

Digite "CONFIRMAR" para prosseguir com a limpeza: 
```

Você digita `CONFIRMAR` e pressiona Enter. O sistema deleta tudo.

**Opção C: Deletar sem confirmação (PARA SCRIPTS/AUTOMAÇÃO):**
```bash
python manage.py limpar_dados_grupo 1 --confirm
```

---

## 📊 Arquivos que foram modificados:

### `agenda/admin.py`
- ✅ Adicionado admin para `Procedimento` com filtro por `group`
- ✅ Adicionado admin para `EscalaAnestesiologista` com filtro por `group`

### `financas/admin.py`
- ✅ Adicionado admin melhorado para `ProcedimentoFinancas` com filtro por `group`
- ✅ Adicionado admin para `Despesas` com filtro por `group`
- ✅ Adicionado admin para `DespesasRecorrentes` com filtro por `group`
- ✅ Adicionado admin para `ConciliacaoTentativa`

### `qualidade/admin.py`
- ✅ Admin melhorado para `AvaliacaoRPA`
- ✅ Admin melhorado para `ProcedimentoQualidade`

### `agenda/management/commands/limpar_dados_grupo.py`
- ✅ Novo comando Django para limpeza automatizada

---

## 🔗 Dependências (Cascade Delete)

```
Grupo (GAZO)
├── Procedimento (deletado)
│   ├── AvaliacaoRPA (deletado em cascata via ON_DELETE=CASCADE)
│   ├── ProcedimentoQualidade (deletado em cascata via ON_DELETE=CASCADE)
│   ├── Despesas (deletado em cascata via ON_DELETE=SET_NULL depois)
│   └── ProcedimentoFinancas (deletado em cascata via ON_DELETE=SET_NULL depois)
│
├── EscalaAnestesiologista (deletado)
│
├── Despesas (deletado)
│
├── DespesasRecorrentes (deletado)
│
└── ProcedimentoFinancas (deletado) [orfão após Procedimento ser deletado]
```

---

## ⚡ Resumo das Alterações:

| Arquivo | Mudança |
|---------|---------|
| `agenda/admin.py` | +79 linhas (Procedimento e EscalaAnestesiologista admin) |
| `financas/admin.py` | +50 linhas (Admin melhorado com filtros) |
| `qualidade/admin.py` | +50 linhas (Admin melhorado com fieldsets) |
| `agenda/management/commands/limpar_dados_grupo.py` | +120 linhas (Novo comando) |

---

## 🎯 Recomendação Final

**Use a Opção 2 (Command Script)** porque:
- ✅ Mais segura (confirma antes de deletar)
- ✅ Mais rápida (tudo em uma execução)
- ✅ Rastreável (mostra logs)
- ✅ Sem risco de esquecer algum modelo
- ✅ Pode ser automática (com `--confirm`)
- ✅ Modo DRY-RUN para validar antes

Mas agora que os admins estão melhorados, também funcionam bem para **exclusões pontuais**.
