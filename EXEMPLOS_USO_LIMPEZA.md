# 🚀 Exemplos Práticos - Limpeza de Dados do Grupo

## 1️⃣ Descobrir o ID do Grupo GAZO

```bash
# Entre no shell Django
python manage.py shell
```

Dentro do shell:
```python
from registration.models import Groups

# Listar todos os grupos
for g in Groups.objects.all():
    print(f"ID: {g.id} | Nome: {g.name}")
```

Saída esperada:
```
ID: 1 | Nome: GAZO
ID: 2 | Nome: OUTRO_GRUPO
ID: 3 | Nome: MAIS_UM_GRUPO
```

Saia do shell:
```python
exit()
```

---

## 2️⃣ Usar o Script de Limpeza

### 2A. PRIMEIRO: Ver o que será deletado (DRY-RUN)
```bash
python manage.py limpar_dados_grupo 1 --dry-run
```

**Saída esperada:**
```
⚠️  AVISO: Você está prestes a deletar TODOS os dados do grupo: GAZO

📊 Registros a serem deletados:

  • Procedimentos: 42
  • Escalas: 15
  • Financeiro: 50
  • Despesas: 8
  • Despesas Recorrentes: 3

  TOTAL: 118 registros

✓ Modo DRY-RUN: Nenhum dados foi deletado
```

---

### 2B. SEGUNDO: Deletar com Confirmação (RECOMENDADO)

```bash
python manage.py limpar_dados_grupo 1
```

**Processo:**
1. Mostra os registros que será deletados
2. Pede que você digite `CONFIRMAR` para prosseguir
3. Se digitar corretamente, deleta tudo
4. Se cancelar, nada é deletado

**Exemplo:**
```
⚠️  AVISO: Você está prestes a deletar TODOS os dados do grupo: GAZO

📊 Registros a serem deletados:

  • Procedimentos: 42
  • Escalas: 15
  • Financeiro: 50
  • Despesas: 8
  • Despesas Recorrentes: 3

  TOTAL: 118 registros

Digite "CONFIRMAR" para prosseguir com a limpeza: CONFIRMAR

🗑️  Deletando dados...

  ✓ Despesas Recorrentes deletadas
  ✓ Procedimentos deletados (e todos os registros relacionados)
  ✓ Escalas deletadas
  ✓ Registros Financeiros deletados

✓ Limpeza concluída com sucesso!

📝 LOG DE LIMPEZA
   Data/Hora: 28/10/2025 14:35:22
   Grupo: GAZO (ID: 1)
   Total de registros deletados: 118
```

---

### 2C. Deletar sem Confirmação (Para Automação)

```bash
python manage.py limpar_dados_grupo 1 --confirm
```

**Nota:** Use apenas em scripts automáticos! Não pede confirmação, deleta direto.

---

## 3️⃣ O que é Deletado

Quando você roda `python manage.py limpar_dados_grupo 1`:

```
✅ DELETADO
├── 📋 Procedimentos (e tudo relacionado)
├── 📅 Escalas de Anestesiologistas
├── 💰 Financeiro dos Procedimentos
├── 💵 Despesas Simples
└── 💸 Despesas Recorrentes

🔗 DELETADOS AUTOMATICAMENTE (via CASCADE)
├── ⭐ Avaliações RPA (OneToOne com Procedimento)
└── 📊 Qualidade dos Procedimentos (OneToOne com Procedimento)
```

---

## 4️⃣ Casos de Uso

### Caso 1: Limpar apenas para validar
```bash
# Veja quantos registros tem
python manage.py limpar_dados_grupo 1 --dry-run
```

### Caso 2: Limpar de verdade com segurança
```bash
# Confirma antes de deletar
python manage.py limpar_dados_grupo 1
```

### Caso 3: Limpar múltiplos grupos (em loop)
```bash
# Crie um arquivo cleanup.sh
for group_id in 1 2 3; do
    echo "Limpando grupo $group_id..."
    python manage.py limpar_dados_grupo $group_id --confirm
done
```

---

## 5️⃣ Troubleshooting

### Erro: "Grupo com ID X não encontrado"
```
Solução: Verifique o ID correto com:
python manage.py shell
>>> from registration.models import Groups
>>> Groups.objects.all().values('id', 'name')
```

### Erro: "Command not found"
```
Solução: Certifique-se de que os arquivos estão no lugar certo:
✓ agenda/management/__init__.py
✓ agenda/management/commands/__init__.py
✓ agenda/management/commands/limpar_dados_grupo.py
```

### Digitou errado a confirmação
```
Você digitou algo que não é "CONFIRMAR" exatamente:
"Operação cancelada"

Nenhum dado foi deletado. Tente novamente.
```

---

## 🎯 Checklist Rápido

- [ ] Descobri o ID do grupo (1, 2, 3, etc)
- [ ] Rodei `--dry-run` para validar quantos registros
- [ ] Confirmei que é MESMO o grupo que quer limpar
- [ ] Executei sem `--dry-run` e digitei `CONFIRMAR`
- [ ] Verificai que os dados foram deletados

---

## 📞 Contato

Se tiver dúvidas, execute:
```bash
python manage.py limpar_dados_grupo --help
```

Ele mostrará todas as opções disponíveis.
