from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from agenda.models import Procedimento, EscalaAnestesiologista
from financas.models import ProcedimentoFinancas, Despesas, DespesasRecorrentes, ConciliacaoTentativa
from qualidade.models import AvaliacaoRPA, ProcedimentoQualidade
from registration.models import Groups
from datetime import datetime


class Command(BaseCommand):
    help = 'Limpa todos os registros de agenda, financeiro e qualidade para um grupo específico'

    def add_arguments(self, parser):
        parser.add_argument(
            'group_id',
            type=int,
            help='ID do grupo a ser limpo'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirma a execução sem pedir confirmação adicional'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula a limpeza sem deletar nada'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        group_id = options['group_id']
        dry_run = options.get('dry_run', False)
        confirm = options.get('confirm', False)

        try:
            group = Groups.objects.get(id=group_id)
        except Groups.DoesNotExist:
            raise CommandError(f'Grupo com ID {group_id} não encontrado')

        self.stdout.write(
            self.style.WARNING(f'\n⚠️  AVISO: Você está prestes a deletar TODOS os dados do grupo: {group.name}')
        )

        # Coleta estatísticas
        stats = self._collect_stats(group)
        self._print_stats(stats)

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n✓ Modo DRY-RUN: Nenhum dado foi deletado'))
            return

        if not confirm:
            confirmacao = input('\nDigite "CONFIRMAR" para prosseguir com a limpeza: ')
            if confirmacao != 'CONFIRMAR':
                self.stdout.write(self.style.ERROR('Operação cancelada'))
                return

        try:
            self._delete_data(group, stats)
            self.stdout.write(self.style.SUCCESS('\n✓ Limpeza concluída com sucesso!'))
            self._log_cleanup(group, stats)
        except Exception as e:
            raise CommandError(f'Erro durante a limpeza: {str(e)}')

    def _collect_stats(self, group):
        """Coleta números de registros a serem deletados"""
        return {
            'procedimentos': Procedimento.objects.filter(group=group).count(),
            'escalas': EscalaAnestesiologista.objects.filter(group=group).count(),
            'financas': ProcedimentoFinancas.objects.filter(group=group).count(),
            'despesas': Despesas.objects.filter(group=group).count(),
            'despesas_recorrentes': DespesasRecorrentes.objects.filter(group=group).count(),
        }

    def _print_stats(self, stats):
        """Exibe estatísticas de forma formatada"""
        self.stdout.write('\n📊 Registros a serem deletados:\n')
        self.stdout.write(f'  • Procedimentos: {stats["procedimentos"]}')
        self.stdout.write(f'  • Escalas: {stats["escalas"]}')
        self.stdout.write(f'  • Financeiro: {stats["financas"]}')
        self.stdout.write(f'  • Despesas: {stats["despesas"]}')
        self.stdout.write(f'  • Despesas Recorrentes: {stats["despesas_recorrentes"]}')
        
        total = sum(stats.values())
        self.stdout.write(self.style.WARNING(f'\n  TOTAL: {total} registros'))

    def _delete_data(self, group, stats):
        """Deleta os dados"""
        self.stdout.write('\n🗑️  Deletando dados...\n')

        # 1. Despesas Recorrentes
        DespesasRecorrentes.objects.filter(group=group).delete()
        self.stdout.write('  ✓ Despesas Recorrentes deletadas')

        # 2. Procedimentos (cascade delete cuidará de relacionados)
        Procedimento.objects.filter(group=group).delete()
        self.stdout.write('  ✓ Procedimentos deletados (e todos os registros relacionados)')

        # 3. Escalas
        EscalaAnestesiologista.objects.filter(group=group).delete()
        self.stdout.write('  ✓ Escalas deletadas')

        # 4. Financeiro orfão (procedimentos já deletados)
        ProcedimentoFinancas.objects.filter(group=group).delete()
        self.stdout.write('  ✓ Registros Financeiros deletados')

    def _log_cleanup(self, group, stats):
        """Log da limpeza realizada"""
        total = sum(stats.values())
        log_message = (
            f'\n📝 LOG DE LIMPEZA\n'
            f'   Data/Hora: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n'
            f'   Grupo: {group.name} (ID: {group.id})\n'
            f'   Total de registros deletados: {total}\n'
        )
        self.stdout.write(self.style.SUCCESS(log_message))


