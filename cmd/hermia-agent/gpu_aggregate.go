package main

import (
	"strconv"
	"strings"
)

type pdhSample struct {
	instance string
	value    float64
}

type parsedInstance struct {
	physIdx int
	gpuIdx  int
	engType string
}

func parseInstanceName(name string) parsedInstance {
	p := parsedInstance{engType: "Other"}

	if i := strings.Index(name, "phys_"); i != -1 {
		rest := name[i+5:]
		if end := strings.Index(rest, "_"); end != -1 {
			rest = rest[:end]
		}
		if v, err := strconv.Atoi(rest); err == nil {
			p.physIdx = v
		}
	}

	if i := strings.Index(name, "gpu_"); i != -1 {
		rest := name[i+4:]
		if end := strings.Index(rest, "_"); end != -1 {
			rest = rest[:end]
		}
		if v, err := strconv.Atoi(rest); err == nil {
			p.gpuIdx = v
		}
	}

	if i := strings.Index(name, "engtype_"); i != -1 {
		rest := name[i+8:]
		// delimit at the next underscore so a future suffix (e.g. "3D_v2")
		// doesn't cause silent misclassification to "Other"
		if end := strings.Index(rest, "_"); end != -1 {
			rest = rest[:end]
		}
		switch rest {
		case "3D", "Compute", "Copy", "VideoDecode", "VideoEncode":
			p.engType = rest
		}
	}

	return p
}

func aggregateEngineCounters(samples []pdhSample) map[string]float64 {
	engines := make(map[string]float64)
	for _, s := range samples {
		p := parseInstanceName(s.instance)
		engines[p.engType] += s.value
	}
	return engines
}
