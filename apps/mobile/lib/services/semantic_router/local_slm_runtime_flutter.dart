import 'local_slm_runtime_contract.dart';
import 'local_slm_runtime_stub.dart'
    if (dart.library.io) 'local_slm_runtime_io.dart' as implementation;

SemanticSlmRuntime createRuntime() => implementation.createRuntime();
