"""
1113333355555

Demo Script - Simple test chain
Shows basic step chain functionality.
222
Steps:
  0: IDLE
 10: COUNT
 20: WAIT
 30: NOTIFY
"""

def demo_chain(ctx):
    """Simple demonstration chain."""
    
    step = ctx.step
    
    if step == 0:  # IDLE
        ctx.update_ui("status", "Demo: Idle")
        ctx.update_ui("instruction", "Press start to begin demo")
        
        # Auto-start after 2 seconds
        if ctx.step_time() > 2.0:
            ctx.log("Auto-starting demo...")
            ctx.goto(10)
    
    elif step == 10:  # COUNT
        ctx.update_ui("status", "Demo: Counting")
        
        # Initialize counter
        if "counter" not in ctx.data:
            ctx.data["counter"] = 0
        
        ctx.data["counter"] += 1
        count = ctx.data["counter"]
        
        ctx.update_ui("instruction", f"Count: {count}")
        ctx.log(f"Counter: {count}")
        
        if count >= 5:
            ctx.goto(20)
    
    elif step == 20:  # WAIT
        ctx.update_ui("status", "Demo: Waiting")
        ctx.update_ui("instruction", f"Waiting... {ctx.step_time():.1f}s")
        
        if ctx.timeout(3.0):
            ctx.goto(30)
    
    elif step == 30:  # NOTIFY
        ctx.update_ui("status", "Demo: Complete")
        ctx.update_ui("instruction", "Demo cycle completed!")
        
        ctx.log_success("Demo completed successfully")
        ctx.notify(f"Completed {ctx.data.get('counter', 0)} cycles", "positive")
        
        if ctx.timeout(2.0):
            ctx.data.clear()
            ctx.goto(0)
    
    else:
        ctx.error(f"Unknown step: {step}")
        ctx.goto(0)


# Export
chain = demo_chain
