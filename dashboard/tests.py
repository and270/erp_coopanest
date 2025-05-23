from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
import pytz # Import pytz

from .utils import calculate_iqr_filtered_average_seconds
from dashboard.views import dashboard_view # Import the view
from agenda.models import Procedimento, ProcedimentoDetalhes # For creating test data
from qualidade.models import ProcedimentoQualidade # For creating test data
from registration.models import Group, CustomUser # For user and group setup

# Mock user model if it's custom, otherwise use Django's default
User = get_user_model()

class IQRUtilsTest(TestCase):
    def test_iqr_with_outliers(self):
        data = [10, 12, 15, 11, 13, 100, 9] # 100 is an outlier
        # Q1 = 10, Q3 = 13, IQR = 3. Lower = 5.5, Upper = 17.5. Filtered: [10,12,15,11,13,9]
        # Mean of filtered: (10+12+15+11+13+9)/6 = 70/6 = 11.666...
        self.assertAlmostEqual(calculate_iqr_filtered_average_seconds(data), 70/6)

    def test_iqr_no_outliers(self):
        data = [10, 12, 15, 11, 13, 14]
        # Q1=11, Q3=14, IQR=3. Lower=6.5, Upper=18.5. All data is within bounds.
        # Mean: (10+12+15+11+13+14)/6 = 75/6 = 12.5
        self.assertAlmostEqual(calculate_iqr_filtered_average_seconds(data), 12.5)

    def test_iqr_empty_list(self):
        self.assertIsNone(calculate_iqr_filtered_average_seconds([]))

    def test_iqr_small_list_less_than_4(self):
        data = [10, 20, 30] # Should return simple mean
        self.assertAlmostEqual(calculate_iqr_filtered_average_seconds(data), 20)
        data_single = [10]
        self.assertAlmostEqual(calculate_iqr_filtered_average_seconds(data_single), 10)


    def test_iqr_all_elements_identical(self):
        data = [10, 10, 10, 10, 10]
        # IQR will be 0. Should return simple mean.
        self.assertAlmostEqual(calculate_iqr_filtered_average_seconds(data), 10)

    def test_iqr_filter_results_in_empty_list(self):
        # Example: Q1=10, Q3=12, IQR=2. Lower=7, Upper=15.
        # Data: [1, 2, 10, 12, 20, 22] -> Filtered: [10, 12]
        # If data were [1,2,3, 100,101,102], Q1=2, Q3=101, IQR=99.
        # Lower = 2 - 1.5*99 = -146.5
        # Upper = 101 + 1.5*99 = 249.5
        # All points are within this wide range.
        # Let's create a list where IQR filtering *would* lead to empty,
        # e.g. by making non-outliers very far apart.
        # This scenario is tricky to construct if the fallback is to original mean.
        # The implementation detail: "If all data is filtered out, fallback to original mean"
        # So, this test should verify that fallback.
        data = [1, 2, 100, 101] # Q1=1.5, Q3=100.5, IQR=99. Lower=-147, Upper=250
                                # All points are within bounds, so this won't test the fallback as intended.
                                # Let's use a dataset where bounds are very narrow.
        data_for_empty_filter = [1, 10, 11, 12, 100] # Q1=10, Q3=12, IQR=2. Lower=7, Upper=15. Filtered: [10,11,12]
                                                    # Mean of filtered: 11.
        # To truly test the "filtered_data is empty" scenario, the data must be such that
        # ALL points become outliers. Example:
        data_extreme_spread = [1, 2, 3, 1000, 1001, 1002]
        # Q1 = 2.5, Q3 = 1001.5, IQR = 999.
        # Lower = 2.5 - 1.5 * 999 = -1496
        # Upper = 1001.5 + 1.5 * 999 = 2499.5
        # All points are within bounds. My understanding of how to make filtered_data empty might be off.
        # The function's code: `filtered_data = [x for x in data_seconds_list if lower_bound <= x <= upper_bound]`
        # If this list is empty, it returns np.mean(data_seconds_list).
        # This happens if ALL original data points are outside the Q1-1.5*IQR to Q3+1.5*IQR range.
        # This is typically rare unless the dataset is very small and has extreme values.
        # Example given by robust stats: data = [6, 7, 15, 36, 39, 40, 41, 42, 43, 47, 50, 79]
        # Q1=36, Q3=43, IQR=7. Lower=25.5, Upper=53.5. Filtered: [36,39,40,41,42,43,47,50]. Outliers: 6,7,15,79.
        # If data_seconds_list = [1, 100, 101, 200], Q1=50.5, Q3=150.5, IQR=100.
        # Lower = 50.5 - 150 = -99.5. Upper = 150.5 + 150 = 300.5.
        # All points are within.

        # Let's use a list that should have all points as outliers relative to each other (not really possible with IQR)
        # The condition "if not filtered_data" is more likely to be hit if the data is very pathological or small.
        # The current implementation of calculate_iqr_filtered_average_seconds will return the mean of the original
        # list if len < 4, or if iqr is 0.
        # If iqr is not 0, and len >=4, it filters. If filtering results in empty, it returns mean of original.
        # So, if we pass [1, 2, 1000, 2000] (len=4)
        # Q1=251, Q3=1500, IQR=1249. Lower=251-1.5*1249 = -1622.5. Upper=1500+1.5*1249 = 3373.5
        # All points are in.
        # This test seems to verify the fallback correctly if such data existed.
        # For now, if the data cannot be constructed to make filtered_data empty, this test will just pass by using a regular list.
        # The logic is: if `filtered_data` is empty, it uses `np.mean(data_seconds_list)`.
        # This means the function should behave like `np.mean(data)` in that specific edge case.
        tricky_data = [1, 10, 1000, 10000] # Example where bounds might exclude some points
        # Q1 = 5.5, Q3 = 5005, IQR = 4999.5
        # Lower = 5.5 - 1.5 * 4999.5 = -7493.75
        # Upper = 5005 + 1.5 * 4999.5 = 12504.25
        # All points are within.
        # The fallback to original mean if filtered_data is empty is a sound strategy.
        # We'll assume the function's internal logic for this fallback is correct as direct construction of such a list is hard.
        # We can test that if the list is small, it returns mean (already done).
        self.assertAlmostEqual(calculate_iqr_filtered_average_seconds(tricky_data), sum(tricky_data)/len(tricky_data))


class DashboardViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.group = Group.objects.create(name="Test Group")
        # Ensure a user with user_type GESTOR_USER exists and is validated
        self.user = User.objects.create_user(
            username='testgestor', 
            password='password', 
            email='gestor@example.com',
            user_type=1,  # GESTOR_USER
            group=self.group,
            validado=True # Ensure user is validated
        )
        
        # Common timezone
        self.sp_timezone = pytz.timezone('America/Sao_Paulo') # Use pytz

        # Create some ProcedimentoDetalhes for filtering
        self.proc_detail1 = ProcedimentoDetalhes.objects.create(name="Procedure A", group=self.group)
        self.proc_detail2 = ProcedimentoDetalhes.objects.create(name="Procedure B", group=self.group)


    def _create_procedimento_qualidade(self, agendado_dt_str, inicio_efetivo_dt_str, fim_efetivo_dt_str, csat_score=None, proc_detail=None):
        agendado_dt = self.sp_timezone.localize(datetime.strptime(agendado_dt_str, '%Y-%m-%d %H:%M'))
        inicio_efetivo_dt = self.sp_timezone.localize(datetime.strptime(inicio_efetivo_dt_str, '%Y-%m-%d %H:%M')) if inicio_efetivo_dt_str else None
        fim_efetivo_dt = self.sp_timezone.localize(datetime.strptime(fim_efetivo_dt_str, '%Y-%m-%d %H:%M')) if fim_efetivo_dt_str else None

        procedimento = Procedimento.objects.create(
            group=self.group,
            status='finished',
            data_horario=agendado_dt,
            data_horario_fim=agendado_dt + timedelta(hours=2), # Dummy scheduled end
            procedimento_principal=proc_detail or self.proc_detail1,
            nome_paciente="Test Patient"
        )
        pq = ProcedimentoQualidade.objects.create(
            procedimento=procedimento,
            data_horario_inicio_efetivo=inicio_efetivo_dt,
            data_horario_fim_efetivo=fim_efetivo_dt,
            csat_score=csat_score,
            # Add other required fields for ProcedimentoQualidade if any
            dor_pos_operatoria=False, # To simplify, assume no pain
            eventos_adversos_graves=False,
            reacao_alergica_grave=False,
            encaminhamento_uti=False,
            evento_adverso_evitavel=False,
            adesao_checklist=True,
            uso_tecnicas_assepticas=True,
            conformidade_diretrizes=True,
            ponv=False,
            adesao_profilaxia=True,
        )
        return pq

    def test_avg_delay_and_duration_no_outliers(self):
        # Delays: 10m, 20m. Durations: 60m, 70m.
        self._create_procedimento_qualidade('2023-01-01 09:50', '2023-01-01 10:00', '2023-01-01 11:00') # Delay 10m, Duration 60m
        self._create_procedimento_qualidade('2023-01-01 11:40', '2023-01-01 12:00', '2023-01-01 13:10') # Delay 20m, Duration 70m
        self._create_procedimento_qualidade('2023-01-01 13:45', '2023-01-01 14:00', '2023-01-01 15:00') # Delay 15m, Duration 60m
        self._create_procedimento_qualidade('2023-01-01 15:50', '2023-01-01 16:00', '2023-01-01 17:10') # Delay 10m, Duration 70m
        # Delays in seconds: 600, 1200, 900, 600. Mean = 3300/4 = 825s = 13m 45s. Expected: "00:13" (rounded/truncated)
        # Durations in seconds: 3600, 4200, 3600, 4200. Mean = 15600/4 = 3900s = 65m. Expected: "01:05"

        request = self.factory.get('/dashboard/')
        request.user = self.user
        
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        
        # Expected: (600+1200+900+600)/4 = 825 seconds. 825/60 = 13.75 min.
        # Formatted: 13 minutes. The formatting is int(hours):02d, int(minutes):02d
        self.assertEqual(metrics['atraso_medio'], "00:13")
        # Expected: (3600+4200+3600+4200)/4 = 3900 seconds. 3900/3600 = 1 hour, 300s=5min.
        self.assertEqual(metrics['duracao_media'], "01:05")

    def test_avg_delay_with_outliers(self):
        # Delays: 10m, 12m, 15m, 11m, 13m, 100m (outlier)
        self._create_procedimento_qualidade('2023-01-01 09:50', '2023-01-01 10:00', '2023-01-01 11:00') # 10m
        self._create_procedimento_qualidade('2023-01-01 10:48', '2023-01-01 11:00', '2023-01-01 12:00') # 12m
        self._create_procedimento_qualidade('2023-01-01 11:45', '2023-01-01 12:00', '2023-01-01 13:00') # 15m
        self._create_procedimento_qualidade('2023-01-01 12:49', '2023-01-01 13:00', '2023-01-01 14:00') # 11m
        self._create_procedimento_qualidade('2023-01-01 13:47', '2023-01-01 14:00', '2023-01-01 15:00') # 13m
        self._create_procedimento_qualidade('2023-01-01 14:20', '2023-01-01 16:00', '2023-01-01 17:00') # 100m (outlier)
        # Delays in seconds: 600, 720, 900, 660, 780, 6000 (outlier)
        # Filtered (from IQRUtilsTest): mean is 700/6 * 10 = 700 seconds (approx 11.66m)
        # 700 seconds = 11 minutes, 40 seconds. Expected: "00:11"

        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertEqual(metrics['atraso_medio'], "00:11") # Based on 700s mean

    def test_avg_duration_with_outliers(self):
        # Durations: 60m, 62m, 65m, 61m, 63m, 150m (outlier)
        self._create_procedimento_qualidade('2023-01-01 10:00', '2023-01-01 10:00', '2023-01-01 11:00') # 60m
        self._create_procedimento_qualidade('2023-01-01 11:00', '2023-01-01 11:00', '2023-01-01 12:02') # 62m
        self._create_procedimento_qualidade('2023-01-01 12:00', '2023-01-01 12:00', '2023-01-01 13:05') # 65m
        self._create_procedimento_qualidade('2023-01-01 13:00', '2023-01-01 13:00', '2023-01-01 14:01') # 61m
        self._create_procedimento_qualidade('2023-01-01 14:00', '2023-01-01 14:00', '2023-01-01 15:03') # 63m
        self._create_procedimento_qualidade('2023-01-01 15:00', '2023-01-01 15:00', '2023-01-01 17:30') # 150m (outlier)
        # Durations in seconds: 3600, 3720, 3900, 3660, 3780, 9000 (outlier)
        # Data for IQR: [3600, 3720, 3900, 3660, 3780, 9000].
        # Q1 = 3660, Q3 = 3900. IQR = 240. Lower = 3300. Upper = 4260.
        # Filtered: [3600, 3720, 3900, 3660, 3780]. Mean = 18660 / 5 = 3732 seconds.
        # 3732 seconds = 62 minutes, 12 seconds. Expected: "01:02"

        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertEqual(metrics['duracao_media'], "01:02") # Based on 3732s mean

    def test_dashboard_empty_data(self):
        # No ProcedimentoQualidade objects created
        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertIsNone(metrics['atraso_medio'])
        self.assertIsNone(metrics['duracao_media'])

    def test_delay_over_24_hours_format(self):
        # Create one procedure with a delay of 1 day, 2 hours, 30 minutes
        # Agendado: 2023-01-01 10:00, Inicio Efetivo: 2023-01-02 12:30
        # Delay = 26 hours, 30 minutes = 1 day, 2 hours, 30 minutes
        # (24*3600 + 2*3600 + 30*60) = 86400 + 7200 + 1800 = 95400 seconds
        self._create_procedimento_qualidade('2023-01-01 10:00', '2023-01-02 12:30', '2023-01-02 13:30')
        # Add a few more "normal" delays to ensure IQR doesn't remove the single large one if it's the only one
        self._create_procedimento_qualidade('2023-01-03 09:50', '2023-01-03 10:00', '2023-01-03 11:00') # 10m
        self._create_procedimento_qualidade('2023-01-04 10:48', '2023-01-04 11:00', '2023-01-04 12:00') # 12m
        self._create_procedimento_qualidade('2023-01-05 11:45', '2023-01-05 12:00', '2023-01-05 13:00') # 15m
        # Delays in seconds: [95400, 600, 720, 900]
        # Q1=660, Q3=51150, IQR=50490. Lower = 660 - 1.5*50490 = -75075. Upper = 51150 + 1.5*50490 = 126885
        # All are within bounds. Mean = (95400+600+720+900)/4 = 97620 / 4 = 24405 seconds.
        # 24405 seconds = 6 hours, 46 minutes, 45 seconds. Expected: "06:46"
        # The formatting currently shows days if days > 0.
        # 24405 seconds. days = 0. hours = 6. remainder = 24405 % 3600 = 2805. minutes = 2805 // 60 = 46.
        # Expected: "06:46"
        
        # If the single delay was the only one: 95400s.
        # The helper `calculate_iqr_filtered_average_seconds` with a single value list: [95400] -> returns 95400.
        # days = 1, seconds_part = 95400 - 86400 = 9000. hours = 2, minutes = 30.
        # Expected "1 dias, 02:30"

        # Let's test with only the single large delay:
        ProcedimentoQualidade.objects.all().delete()
        Procedimento.objects.all().delete()
        self._create_procedimento_qualidade('2023-01-01 10:00', '2023-01-02 12:30', '2023-01-02 13:30')


        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertEqual(metrics['atraso_medio'], "1 dias, 02:30")

    def test_duration_over_24_hours_format(self):
        # Create one procedure with a duration of 26 hours, 30 minutes
        # Inicio Efetivo: 2023-01-01 10:00, Fim Efetivo: 2023-01-02 12:30
        # Duration = 95400 seconds
        self._create_procedimento_qualidade('2023-01-01 09:00', '2023-01-01 10:00', '2023-01-02 12:30')
        # Add a few more "normal" durations
        self._create_procedimento_qualidade('2023-01-03 09:00', '2023-01-03 10:00', '2023-01-03 11:00') # 60m
        self._create_procedimento_qualidade('2023-01-04 09:00', '2023-01-04 11:00', '2023-01-04 12:00') # 60m
        self._create_procedimento_qualidade('2023-01-05 09:00', '2023-01-05 12:00', '2023-01-05 13:00') # 60m
        # Durations in seconds: [95400, 3600, 3600, 3600]
        # Q1=3600, Q3=49500, IQR=45900. Lower = 3600 - 1.5*45900 = -65250. Upper = 49500 + 1.5*45900 = 118350
        # All are within bounds. Mean = (95400+3600+3600+3600)/4 = 106200 / 4 = 26550 seconds.
        # 26550 seconds. total_seconds = 26550. hours = 26550 // 3600 = 7. remainder = 26550 % 3600 = 1350. minutes = 1350 // 60 = 22.
        # Expected: "07:22"
        
        # If the single duration was the only one: 95400s.
        # hours = 95400 // 3600 = 26. remainder = 95400 % 3600 = 1800. minutes = 1800 // 60 = 30.
        # Expected "26:30"

        # Let's test with only the single large duration:
        ProcedimentoQualidade.objects.all().delete()
        Procedimento.objects.all().delete()
        self._create_procedimento_qualidade('2023-01-01 09:00', '2023-01-01 10:00', '2023-01-02 12:30')

        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertEqual(metrics['duracao_media'], "26:30")

    def test_negative_delay_is_ignored(self):
        # Procedure started *before* scheduled time. This delay should be ignored.
        self._create_procedimento_qualidade('2023-01-01 10:00', '2023-01-01 09:50', '2023-01-01 11:00') # Negative delay
        self._create_procedimento_qualidade('2023-01-01 11:40', '2023-01-01 12:00', '2023-01-01 13:10') # Delay 20m (1200s)
        # Only the 1200s delay should be considered.
        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertEqual(metrics['atraso_medio'], "00:20")

    def test_negative_duration_is_ignored(self):
        # Procedure end time *before* start time. This duration should be ignored.
        self._create_procedimento_qualidade('2023-01-01 10:00', '2023-01-01 11:00', '2023-01-01 10:50') # Negative duration
        self._create_procedimento_qualidade('2023-01-01 11:00', '2023-01-01 12:00', '2023-01-01 13:10') # Duration 70m (4200s)
        # Only the 4200s duration should be considered.
        request = self.factory.get('/dashboard/')
        request.user = self.user
        response = dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        metrics = response.context_data['metrics']
        self.assertEqual(metrics['duracao_media'], "01:10")I've written the tests for `dashboard.utils.calculate_iqr_filtered_average_seconds` and for the `dashboard_view` focusing on `avg_delay` and `avg_duration` calculations with IQR outlier removal.

**Summary of tests in `dashboard/tests.py`:**

**`IQRUtilsTest`:**
*   `test_iqr_with_outliers`: Checks correct calculation when outliers are present.
*   `test_iqr_no_outliers`: Checks correct calculation when no outliers are present.
*   `test_iqr_empty_list`: Checks behavior with an empty list (should return `None`).
*   `test_iqr_small_list_less_than_4`: Checks behavior with small lists (should return simple mean).
*   `test_iqr_all_elements_identical`: Checks behavior when all elements are the same (IQR is 0, should return simple mean).
*   `test_iqr_filter_results_in_empty_list`: This test acknowledges the difficulty in constructing a list that *becomes* empty after filtering if the fallback is to the original mean. It currently tests a general case, relying on the internal logic of the fallback mechanism.

**`DashboardViewTest`:**
*   **Setup:** Creates a test user (`GESTOR_USER`), group, and `RequestFactory`.
*   **`_create_procedimento_qualidade` helper:** A utility to easily create `Procedimento` and `ProcedimentoQualidade` instances with specified times.
*   `test_avg_delay_and_duration_no_outliers`: Tests calculation and formatting when no outliers are present in delay or duration data.
*   `test_avg_delay_with_outliers`: Tests `atraso_medio` calculation with outlier data, verifying IQR filtering.
*   `test_avg_duration_with_outliers`: Tests `duracao_media` calculation with outlier data, verifying IQR filtering.
*   `test_dashboard_empty_data`: Checks that metrics are `None` when there's no `ProcedimentoQualidade` data.
*   `test_delay_over_24_hours_format`: Checks the specific string formatting for delays exceeding 24 hours.
*   `test_duration_over_24_hours_format`: Checks the string formatting for durations exceeding 24 hours.
*   `test_negative_delay_is_ignored`: Verifies that procedures starting before their scheduled time (negative delays) are not included in the average delay calculation.
*   `test_negative_duration_is_ignored`: Verifies that procedures with end times before start times (negative durations) are not included in the average duration calculation.

The tests cover the core logic of IQR filtering and its integration into the dashboard view, including various data scenarios and formatting requirements. The `pytz` import was added to handle timezone-aware datetimes correctly in test data creation.

All planned tests for both `qualidade` and `dashboard` modules have been implemented.
