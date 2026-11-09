"""Local dev comparison using a pinned DeepSeek-OCR 2 checkout and original page pixels.

No expected answer is included in the OCR prompt. Results stay on this machine.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import struct
import threading
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if sys.stderr:
    sys.stderr.reconfigure(encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--gpu-gib', type=float, default=4.0)
    parser.add_argument('--placement', choices=['resident-vision', 'auto'], default='resident-vision')
    parser.add_argument('--case', choices=['date', 'header', 'both', 'page'], default='both')
    args = parser.parse_args()
    os.environ['HF_HOME'] = str(Path(args.model).parent / 'hf-cache')
    os.environ['HF_MODULES_CACHE'] = str(Path(args.model).parent / 'hf-cache' / 'modules')
    import psutil
    import torch
    from PIL import Image
    from transformers import AutoModel, AutoTokenizer, TextStreamer
    from accelerate.hooks import remove_hook_from_module

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    image = Image.open(args.image).convert('RGB')
    w, h = image.size
    regions = {'date': (0.50, 0.108, 0.88, 0.145),
               'header': (0.12, 0.048, 0.93, 0.24)}
    cases = ['date', 'header'] if args.case == 'both' else [args.case]
    paths, boxes = {}, {}
    for case in cases:
        if case == 'page':
            paths[case] = Path(args.image)
            boxes[case] = [0, 0, w, h]
        else:
            a, b, c, d = regions[case]
            boxes[case] = [round(a*w), round(b*h), round(c*w), round(d*h)]
            paths[case] = out / f'{case}-input.png'
            image.crop(boxes[case]).save(paths[case])

    assert torch.cuda.is_available(), 'This trial needs the separate CUDA environment'
    torch.set_num_threads(4)
    process = psutil.Process()
    peak_rss = [0]
    sampling = threading.Event()
    def sample():
        while not sampling.wait(0.2):
            peak_rss[0] = max(peak_rss[0], process.memory_info().rss)
    threading.Thread(target=sample, daemon=True).start()

    print(f'GPU: {torch.cuda.get_device_name(0)}; torch={torch.__version__}; free={torch.cuda.mem_get_info()[0]/2**30:.2f} GiB', flush=True)
    print('Loading original BF16 weights with CPU offload...', flush=True)
    started = time.perf_counter()
    placement = 'auto'
    if args.placement == 'resident-vision':
        # Keep the visual encoder and vocabulary head resident. Offloading the
        # latter at every generated token costs more than sparse MoE experts.
        checkpoint = Path(args.model) / 'model-00001-of-000001.safetensors'
        with checkpoint.open('rb') as f:
            header = json.loads(f.read(struct.unpack('<Q', f.read(8))[0]))
        sizes = {}
        for name, spec in header.items():
            if name == '__metadata__':
                continue
            depth = 3 if name.startswith('model.layers.') else 2 if name.startswith('model.') else 1
            module = '.'.join(name.split('.')[:depth])
            sizes[module] = sizes.get(module, 0) + spec['data_offsets'][1] - spec['data_offsets'][0]
        placement = {name: 0 for name in sizes if not name.startswith('model.layers.')}
        resident = sum(sizes[name] for name in placement)
        budget = int(args.gpu_gib * 2**30)
        if resident > budget:
            raise ValueError('GPU budget is too small for the visual encoder and vocabulary modules')
        for name in sorted((n for n in sizes if n.startswith('model.layers.')), key=lambda n: int(n.split('.')[-1])):
            fits = resident + sizes[name] <= budget
            placement[name] = 0 if fits else 'cpu'
            if fits:
                resident += sizes[name]
        print(f'Resident model weights: {resident/2**30:.3f} GiB', flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True, local_files_only=True)
    # The published tokenizer leaves eos_token unset, while infer() strips this token.
    if tokenizer.eos_token_id is None:
        stop_token = '<｜end▁of▁sentence｜>'
        if stop_token not in tokenizer.get_vocab():
            raise RuntimeError('The official stop token is missing from the tokenizer')
        tokenizer.eos_token = stop_token
    model = AutoModel.from_pretrained(args.model, trust_remote_code=True, local_files_only=True,
                                     torch_dtype=torch.bfloat16, _attn_implementation='eager',
                                     low_cpu_mem_usage=True, device_map=placement,
                                     max_memory={0: int(args.gpu_gib*2**30), 'cpu': '12GiB'},
                                     offload_folder=str(out/'offload')).eval()
    # Upstream reads these embedding weights directly instead of calling forward().
    # Accelerate's lazy CPU hooks therefore cannot materialize them on demand.
    # Keep the two tiny, unmodified embeddings resident on CUDA.
    for name in ('query_768', 'query_1024'):
        embedding = getattr(model.model.qwen2_model, name)
        remove_hook_from_module(embedding)
        embedding.to('cuda')
        model.hf_device_map[f'model.qwen2_model.{name}'] = 0
    load_seconds = time.perf_counter() - started
    print(f'Model loaded in {load_seconds:.2f}s; device map: {model.hf_device_map}', flush=True)
    report = {'model': 'deepseek-ai/DeepSeek-OCR-2',
              'revision': 'aaa02f3811945a91062062994c5c4a3f4c0af2b0',
              'prompt': '<image>\nFree OCR.', 'weights': 'BF16 (no quantization)',
              'placement': args.placement,
              'attention': 'eager decoder / SDPA visual encoder',
              'gpu': torch.cuda.get_device_name(0), 'load_seconds': round(load_seconds, 3),
              'source_image': str(Path(args.image).resolve()),
              'source_sha256': hashlib.sha256(Path(args.image).read_bytes()).hexdigest(),
              'device_map': model.hf_device_map, 'results': []}

    generate = model.generate
    token_limit = [96]
    def bounded_generate(*positional, **kwargs):
        kwargs['max_new_tokens'] = token_limit[0]
        kwargs['do_sample'] = False
        kwargs.pop('temperature', None)
        kwargs['attention_mask'] = torch.ones_like(positional[0])
        kwargs['pad_token_id'] = tokenizer.eos_token_id
        kwargs['streamer'] = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=False)
        return generate(*positional, **kwargs)
    model.generate = bounded_generate
    for case in cases:
        token_limit[0] = {'date': 96, 'header': 384, 'page': 3072}[case]
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        print(f'START {case}', flush=True)
        started = time.perf_counter()
        # eval_mode returns text before the upstream optional visualization/eval paths.
        result = model.infer(tokenizer, prompt='<image>\nFree OCR.',
                             image_file=str(paths[case]), output_path=str(out/case),
                             base_size=1024, image_size=1024 if case == 'date' else 768,
                             crop_mode=case != 'date', save_results=False, eval_mode=True)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        text = str(result)
        (out / f'{case}-result.txt').write_text(text, encoding='utf-8')
        report['results'].append({'case': case, 'box': boxes[case], 'seconds': round(elapsed, 3),
                                  'gpu_peak_allocated_gib': round(torch.cuda.max_memory_allocated()/2**30, 3),
                                  'gpu_peak_reserved_gib': round(torch.cuda.max_memory_reserved()/2**30, 3),
                                  'process_peak_ram_gib': round(peak_rss[0]/2**30, 3), 'text': text})
        (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'END {case}: {elapsed:.2f}s', flush=True)
        print(text[:1600], flush=True)
    sampling.set()
    print('TRIAL COMPLETE', flush=True)


if __name__ == '__main__':
    main()
