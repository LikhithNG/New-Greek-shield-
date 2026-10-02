#!/usr/bin/env python3
"""
Enhanced Base Agent with LLM Integration
"""

import os
import sys
from dotenv import load_dotenv
import snowflake.connector
from abc import ABC, abstractmethod
from datetime import datetime
import json
import logging
from typing import Dict, List, Optional, Any

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.llm_manager import get_llm_manager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class BaseAgent(ABC):
    """Base class for all agents with LLM capabilities"""
    
    def __init__(self, agent_name: str, agent_role: str, use_llm: bool = True):
        """
        Initialize base agent
        
        Args:
            agent_name: Unique identifier
            agent_role: Description of responsibility  
            use_llm: Whether to use LLM reasoning (default: True)
        """
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.use_llm = use_llm
        
        self.logger = logging.getLogger(agent_name)
        self.execution_log = []
        self.state = {}
        self.confidence_scores = {}
        
        # Initialize LLM if requested
        if use_llm:
            try:
                self.llm = get_llm_manager('openai')
                self.logger.info(f"🧠 {agent_name} - LLM enabled")
            except Exception as e:
                self.logger.warning(f"⚠️  LLM initialization failed: {e}")
                self.llm = None
                self.use_llm = False
        else:
            self.llm = None
        
        self.logger.info(f"🤖 {agent_name} initialized - Role: {agent_role}")
    
    def get_snowflake_connection(self):
        """Create Snowflake connection"""
        try:
            conn = snowflake.connector.connect(
                user=os.getenv('SNOWFLAKE_USER'),
                password=os.getenv('SNOWFLAKE_PASSWORD'),
                account=os.getenv('SNOWFLAKE_ACCOUNT'),
                warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
                database=os.getenv('SNOWFLAKE_DATABASE'),
                schema=os.getenv('SNOWFLAKE_SCHEMA'),
                role=os.getenv('SNOWFLAKE_ROLE'),
                # Disables TLS certificate checks; opt-in only via env var
                insecure_mode=os.getenv('SNOWFLAKE_INSECURE_MODE', 'false').lower() == 'true',
                client_session_keep_alive=True
            )
            self.logger.info("✅ Connected to Snowflake")
            return conn
        except Exception as e:
            self.logger.error(f"❌ Snowflake connection failed: {e}")
            raise
    
    def log_action(self, action: str, details: Dict):
        """Log agent actions"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'agent': self.agent_name,
            'action': action,
            'details': details
        }
        self.execution_log.append(log_entry)
        self.logger.info(f"📝 {action}: {str(details)[:100]}")
    
    def update_state(self, key: str, value: Any):
        """Update agent's internal state"""
        self.state[key] = value
    
    def get_state(self, key: str, default=None):
        """Get state value"""
        return self.state.get(key, default)
    
    def set_confidence(self, key: str, score: float, reasons: List[str] = None):
        """Set confidence score"""
        self.confidence_scores[key] = {
            'score': max(0, min(100, score)),
            'level': self._confidence_level(score),
            'reasons': reasons or [],
            'timestamp': datetime.now().isoformat()
        }
    
    def _confidence_level(self, score: float) -> str:
        """Convert score to level"""
        if score >= 80:
            return "HIGH"
        elif score >= 60:
            return "MODERATE"
        elif score >= 40:
            return "LOW"
        else:
            return "VERY_LOW"
    
    def query_snowflake(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute SQL query"""
        conn = None
        try:
            conn = self.get_snowflake_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            
            cursor.close()
            self.log_action("Snowflake query executed", {
                'query': query[:100],
                'rows_returned': len(results)
            })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Query failed: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def ask_llm(self, prompt: str, system: Optional[str] = None, 
                temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Ask LLM a question"""
        if not self.use_llm or not self.llm:
            raise RuntimeError(f"{self.agent_name} does not have LLM enabled")
        
        self.log_action("LLM query", {'prompt': prompt[:100]})
        
        response = self.llm.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response
    
    def ask_llm_json(self, prompt: str, system: Optional[str] = None,
                     max_tokens: int = 2000) -> Dict:
        """Ask LLM and get JSON response"""
        if not self.use_llm or not self.llm:
            raise RuntimeError(f"{self.agent_name} does not have LLM enabled")
        
        self.log_action("LLM JSON query", {'prompt': prompt[:100]})
        
        response = self.llm.generate_json(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens
        )
        
        return response
    
    def get_execution_summary(self) -> Dict:
        """Get execution summary"""
        return {
            'agent_name': self.agent_name,
            'agent_role': self.agent_role,
            'total_actions': len(self.execution_log),
            'execution_log': self.execution_log,
            'final_state': self.state,
            'confidence_scores': self.confidence_scores,
            'llm_enabled': self.use_llm
        }
    
    def reset(self):
        """Reset agent"""
        self.execution_log = []
        self.state = {}
        self.confidence_scores = {}
        self.logger.info(f"🔄 {self.agent_name} reset")
    
    @abstractmethod
    def execute(self, context: Dict) -> Dict:
        """Main execution - must be implemented"""
        pass
    
    @abstractmethod
    def validate_input(self, context: Dict) -> bool:
        """Validate input"""
        pass
    
    def safe_execute(self, context: Dict) -> Dict:
        """Safely execute with error handling"""
        try:
            self.logger.info(f"🚀 Starting execution for {self.agent_name}")
            
            if not self.validate_input(context):
                return {
                    'success': False,
                    'error': 'Invalid input context',
                    'agent': self.agent_name
                }
            
            result = self.execute(context)
            
            result['agent'] = self.agent_name
            result['execution_time'] = datetime.now().isoformat()
            result['success'] = True
            result['confidence_scores'] = self.confidence_scores
            
            self.logger.info(f"✅ {self.agent_name} completed")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Execution failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'agent': self.agent_name,
                'execution_time': datetime.now().isoformat()
            }
    
    def __repr__(self):
        return f"<{self.agent_name}: {self.agent_role} | LLM: {self.use_llm}>"


if __name__ == "__main__":
    print("Testing Base Agent with LLM...")
    
    class TestAgent(BaseAgent):
        def __init__(self):
            super().__init__("TestAgent", "Testing", use_llm=True)
        
        def validate_input(self, context):
            return 'question' in context
        
        def execute(self, context):
            question = context['question']
            
            if self.use_llm:
                answer = self.ask_llm(f"Answer briefly: {question}")
                self.set_confidence('answer', 85, ['LLM reasoning'])
            else:
                answer = "LLM not available"
                self.set_confidence('answer', 60, ['Rule-based'])
            
            return {'answer': answer}
    
    try:
        agent = TestAgent()
        result = agent.safe_execute({'question': 'What is Python?'})
        
        print("\n" + "="*60)
        print("TEST RESULTS:")
        print("="*60)
        print(f"Success: {result['success']}")
        print(f"Answer: {result.get('answer', 'N/A')[:100]}")
        print(f"Confidence: {agent.confidence_scores}")
        print("\n✅ Base Agent with LLM working!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")