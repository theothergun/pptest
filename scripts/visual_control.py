"""
Visual Control Station
Camera-based inspection and quality control.

Steps:
  0: IDLE - Waiting for trigger
 10: POSITION_CHECK - Ensure part is positioned correctly
 20: CAPTURE - Take photo with camera
 30: ANALYZE - Process image (AI/CV)
 40: DECISION - Pass/Fail based on analysis
 50: PASS - Good part detected
 60: FAIL - Defect detected
 70: REJECT - Activate reject mechanism
9000: ERROR - Error handling
"""

def visual_control_chain(ctx):
    """Visual inspection station chain."""
    
    step = ctx.step
    
    if step == 0:  # IDLE
        ctx.update_ui("status", "Idle")
        ctx.update_ui("instruction", "Waiting for part...")
        ctx.output("inspection_light", False)
        
        # Wait for part present sensor
        if ctx.input("part_present_sensor"):
            ctx.log("Part detected, starting inspection")
            ctx.goto(10)
    
    elif step == 10:  # POSITION_CHECK
        ctx.update_ui("status", "Checking position...")
        
        # Check if part is properly positioned
        positioned = ctx.input("position_ok_sensor")
        
        if positioned:
            ctx.log("Part positioned correctly")
            ctx.goto(20)
        elif ctx.timeout(3.0):
            ctx.error("Part positioning timeout")
            ctx.goto(9000)
    
    elif step == 20:  # CAPTURE
        ctx.update_ui("status", "Capturing image...")
        ctx.update_ui("instruction", "Do not move part")
        
        # Turn on inspection light
        ctx.output("inspection_light", True)
        
        # Wait for light to stabilize
        if ctx.step_time() > 0.2:
            # Capture image from camera
            image = ctx.camera_capture("inspection_cam")
            
            if image is not None:
                ctx.data["image"] = image
                ctx.data["capture_time"] = ctx.cycle_count
                ctx.log("Image captured successfully")
                ctx.goto(30)
            else:
                ctx.error("Camera capture failed")
                ctx.goto(9000)
    
    elif step == 30:  # ANALYZE
        ctx.update_ui("status", "Analyzing...")
        ctx.update_ui("instruction", "Processing image...")
        
        # Turn off inspection light
        ctx.output("inspection_light", False)
        
        # Simulate AI/CV analysis
        # In real implementation, this would call your vision system
        # result = vision_system.analyze(ctx.data["image"])
        
        # Placeholder: random pass/fail for demo
        import random
        analysis_result = {
            "pass": random.random() > 0.2,  # 80% pass rate
            "defects": [],
            "confidence": 0.95
        }
        
        if not analysis_result["pass"]:
            analysis_result["defects"] = ["scratch", "discoloration"]
        
        ctx.data["analysis"] = analysis_result
        ctx.log(f"Analysis complete: {'PASS' if analysis_result['pass'] else 'FAIL'}")
        
        ctx.goto(40)
    
    elif step == 40:  # DECISION
        ctx.update_ui("status", "Decision...")
        
        result = ctx.data.get("analysis", {})
        passed = result.get("pass", False)
        
        if passed:
            ctx.goto(50)
        else:
            ctx.goto(60)
    
    elif step == 50:  # PASS
        ctx.update_ui("status", "PASS ✓")
        ctx.update_ui("instruction", "Part is good")
        
        ctx.output("pass_light", True)
        ctx.output("fail_light", False)
        
        # Publish pass event
        ctx.publish_event(
            "inspection_pass",
            timestamp=ctx.cycle_count,
            confidence=ctx.data.get("analysis", {}).get("confidence", 0)
        )
        
        ctx.log_success("Part passed inspection")
        
        # Hold result for 1 second
        if ctx.timeout(1.0):
            ctx.output("pass_light", False)
            ctx.data.clear()
            ctx.goto(0)
    
    elif step == 60:  # FAIL
        ctx.update_ui("status", "FAIL ✗")
        
        defects = ctx.data.get("analysis", {}).get("defects", [])
        defect_str = ", ".join(defects) if defects else "Unknown"
        
        ctx.update_ui("instruction", f"Defects: {defect_str}")
        
        ctx.output("pass_light", False)
        ctx.output("fail_light", True)
        
        # Publish fail event
        ctx.publish_event(
            "inspection_fail",
            timestamp=ctx.cycle_count,
            defects=defects
        )
        
        ctx.log(f"Part failed inspection: {defect_str}")
        ctx.alarm(f"DEFECT DETECTED: {defect_str}")
        
        ctx.goto(70)
    
    elif step == 70:  # REJECT
        ctx.update_ui("status", "Rejecting...")
        ctx.update_ui("instruction", "Activating reject mechanism")
        
        # Activate pneumatic reject pusher
        if ctx.step_time() < 0.5:
            ctx.output("reject_pusher", True)
        else:
            ctx.output("reject_pusher", False)
            ctx.output("fail_light", False)
            
            # Wait for part to be removed
            if not ctx.input("part_present_sensor"):
                ctx.log("Defective part rejected")
                ctx.data.clear()
                ctx.goto(0)
            elif ctx.timeout(5.0):
                ctx.error("Part not removed after reject")
                ctx.goto(9000)
    
    elif step == 9000:  # ERROR
        ctx.update_ui("status", "ERROR")
        ctx.update_ui("instruction", ctx.error_message)
        
        # Turn off all outputs
        ctx.output("inspection_light", False)
        ctx.output("pass_light", False)
        ctx.output("reject_pusher", False)
        
        # Flash fail light
        if int(ctx.step_time() * 2) % 2 == 0:
            ctx.output("fail_light", True)
        else:
            ctx.output("fail_light", False)
        
        # Auto-reset after 5 seconds or manual reset
        if ctx.input("reset_button") or ctx.timeout(5.0):
            ctx.clear_error()
            ctx.data.clear()
            ctx.output("fail_light", False)
            ctx.goto(0)
    
    else:
        ctx.error(f"Unknown step: {step}")
        ctx.goto(9000)


# Export
chain = visual_control_chain
