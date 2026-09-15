import 'local_slm_runtime_contract.dart';
import 'local_slm_runtime_stub.dart'
    if (dart.library.ui) 'local_slm_runtime_flutter.dart' as implementation;

export 'local_slm_runtime_contract.dart';

SemanticSlmRuntime createSemanticSlmRuntime() => implementation.createRuntime();
