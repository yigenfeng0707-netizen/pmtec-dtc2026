import sys
print("python", sys.version.split()[0])
for m in ["torch", "transformers", "peft", "accelerate", "datasets", "trl", "liger_kernel"]:
    try:
        mod = __import__(m)
        v = getattr(mod, "__version__", "?")
        extra = ""
        if m == "torch":
            extra = f" cuda={mod.cuda.is_available()} n_gpu={mod.cuda.device_count()}"
        print(f"{m:16} {v}{extra}")
    except Exception as ex:
        print(f"{m:16} MISSING ({type(ex).__name__})")
