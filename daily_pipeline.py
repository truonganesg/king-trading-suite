# =====================================================================
# KING TRADING OS: MASTER AUTONOMOUS PRODUCTION ENGINE
# HEADLESS COMPATIBLE | LINUX UBUNTU & GITHUB ACTIONS CERTIFIED
# =====================================================================
import sys, types

# 🌟 EMULATE GOOGLE.COLAB MODULES FOR HEADLESS LINUX RUNNER
mock_colab = types.ModuleType('google.colab')
mock_data_table = types.ModuleType('google.colab.data_table')
mock_data_table.DataTable = lambda *args, **kwargs: None
mock_data_table.enable_dataframe_formatter = lambda *args, **kwargs: None
mock_colab.data_table = mock_data_table
mock_colab.userdata = types.SimpleNamespace(get=lambda k: "")
sys.modules['google'] = types.ModuleType('google')
sys.modules['google.colab'] = mock_colab
sys.modules['google.colab.data_table'] = mock_data_table

# 🌟 EMULATE IPYTHON DISPLAY FOR HEADLESS TERMINAL
try:
    from IPython.display import display, HTML
except Exception:
    def display(*args, **kwargs): pass
    def HTML(x): return x

