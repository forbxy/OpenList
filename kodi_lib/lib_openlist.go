package main

import "C"
import (
	"fmt"
	"os"
	"path/filepath"
	"runtime/debug"
	"time"

	"github.com/OpenListTeam/OpenList/v4/cmd/flags"
	"github.com/OpenListTeam/OpenList/v4/internal/bootstrap"
	"github.com/sirupsen/logrus"

	_ "github.com/OpenListTeam/OpenList/v4/drivers"
	_ "github.com/OpenListTeam/OpenList/v4/internal/archive"
	_ "github.com/OpenListTeam/OpenList/v4/internal/offline_download"
)

var stopChan = make(chan struct{})

//export OpenList_Start
func OpenList_Start(dataDir *C.char) {
	// 1. Setup panic recovery to prevent crashing Kodi
	defer func() {
		if r := recover(); r != nil {
			// Log panic to a file in dataDir common location or temp if not available
			logPanic(r)
		}
	}()

	// 2. Override logrus exit function to panic instead of os.Exit
	logrus.StandardLogger().ExitFunc = func(int) {
		panic("logrus fatal error")
	}

	if dataDir != nil {
		flags.DataDir = C.GoString(dataDir)
	}

	// Ensure data directory exists
	if flags.DataDir != "" {
		os.MkdirAll(flags.DataDir, 0755)

		// 3. Redirect logrus output to a file
		logPath := filepath.Join(flags.DataDir, "openlist.log")
		f, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
		if err == nil {
			logrus.SetOutput(f)
			// Also redirect stdout/stderr if possible, but logrus is main output
		}
	}

	// Set default flags that CLI would usually set
	flags.Debug = false
	flags.Dev = false

	logrus.Info("Starting OpenList library...")

	bootstrap.Init()
	bootstrap.Start()

	logrus.Info("OpenList started successfully")

	// Block here waiting for stop signal from OpenList_Stop
	<-stopChan

	logrus.Info("Shutting down OpenList library...")
	bootstrap.Shutdown(1 * time.Second)
	bootstrap.Release()
	logrus.Info("OpenList library stopped")
}

func logPanic(r interface{}) {
	msg := fmt.Sprintf("PANIC in OpenList: %v\nStack: %s", r, debug.Stack())

	// Create a crash log file
	path := "openlist_crash.log"
	if flags.DataDir != "" {
		path = filepath.Join(flags.DataDir, "openlist_crash.log")
	} else {
		// Fallback to temp dir
		path = filepath.Join(os.TempDir(), "openlist_crash.log")
	}

	os.WriteFile(path, []byte(msg), 0666)
}

//export OpenList_Stop
func OpenList_Stop() {
	// Non-blocking send to avoid panic if channel is full or closed
	select {
	case stopChan <- struct{}{}:
	default:
	}
}

func main() {}
